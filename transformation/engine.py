import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal

import dlt
import duckdb
import ibis
from ibis.expr import datatypes as dt
from ibis.expr.operations.relations import DatabaseTable, UnboundTable
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import lineage
from sqlglot.schema import MappingSchema

logger = logging.getLogger(__name__)

_validator_con: duckdb.DuckDBPyConnection | None = None
_sqlglot_schema = MappingSchema(dialect="duckdb")
_models: list["ModelDefinition"] = []


def _get_validator_connection() -> duckdb.DuckDBPyConnection:
    """Return the shared in-memory DuckDB session for compile-time DDL verification."""
    global _validator_con
    if _validator_con is None:
        con = duckdb.connect()
        con.execute("ATTACH ':memory:' AS orca; USE orca;")
        _validator_con = con
    return _validator_con


def reset_registry() -> None:
    """Close the validator connection and clear registered models and schemas (for testing)."""
    global _validator_con, _sqlglot_schema
    if _validator_con is not None:
        _validator_con.close()
        _validator_con = None
    _sqlglot_schema = MappingSchema(dialect="duckdb")
    _models.clear()


@dataclass(frozen=True)
class ModelDefinition:
    """Compiled transformation model verified against Ibis types and DuckDB DDL."""

    name: str
    db_schema: str
    materialized: Literal["view", "table"]
    description: str
    expr: ibis.Table
    sql: str
    ibis_schema: ibis.Schema
    deps: tuple[tuple[str, str], ...]
    column_lineage: dict[str, list[tuple[str, str, str]]]
    unique: tuple[str, ...]
    not_null: tuple[str, ...]
    columns: dict[str, str]

    @property
    def table(self) -> ibis.Table:
        """Return an unbound Ibis table expression referencing this model."""
        return ibis.table(self.ibis_schema, name=self.name, database=self.db_schema)


@dataclass(frozen=True)
class MaterializationStats:
    """Execution metrics and check counts produced by materializing a model."""

    row_count: int
    null_counts: dict[str, int]
    duplicate_counts: dict[str, int]


def get_models(*_modules: ModuleType) -> tuple[ModelDefinition, ...]:
    """Return all registered transformation models in registration order.

    Callers may pass imported model modules (e.g. ``get_models(marts)``) to ensure those
    modules are loaded before reading the registry.
    """
    return tuple(_models)


def register_dlt_source(
    source: Any, *, db_schema: str = "raw"
) -> dict[str, ibis.Table]:
    """Register a dlt source's static table schemas for offline type and DDL verification.

    Derives table schemas from `source.discover_schema()` (which reflects static `columns=`
    declarations and omits runtime `_dlt_*` columns and unhinted dynamic resources), seeds
    stub tables into the in-memory DuckDB validator and sqlglot schema map, and returns
    unbound Ibis tables keyed by table name.
    """
    discovered_schema = source.discover_schema()
    normalized_schema = discovered_schema.naming.normalize_tables_path(db_schema)

    # dlt's DuckDB/DuckLake destination defaults timestamp columns to TIMESTAMPTZ unless timezone=False.
    for tbl_meta in discovered_schema.tables.values():
        for col_meta in tbl_meta.get("columns", {}).values():
            if (
                col_meta.get("data_type") == "timestamp"
                and col_meta.get("timezone") is not False
            ):
                col_meta["timezone"] = True

    dataset = dlt.dataset("ducklake", normalized_schema, schema=discovered_schema)
    validator_con = _get_validator_connection()
    escaped_schema = normalized_schema.replace('"', '""')
    validator_con.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"')

    tables: dict[str, ibis.Table] = {}
    schema_tables = dataset.sqlglot_schema.mapping.get(normalized_schema, {})
    for tbl_name, cols in schema_tables.items():
        if tbl_name.startswith("_dlt") or not cols:
            continue
        escaped_table = tbl_name.replace('"', '""')
        col_defs = [
            exp.ColumnDef(
                this=exp.to_identifier(col_name, quoted=True), kind=dtype
            ).sql("duckdb")
            for col_name, dtype in cols.items()
        ]
        validator_con.execute(
            f'CREATE OR REPLACE TABLE "{escaped_schema}"."{escaped_table}" ({", ".join(col_defs)})'
        )
        _sqlglot_schema.add_table(
            exp.Table(
                this=exp.to_identifier(tbl_name, quoted=True),
                db=exp.to_identifier(normalized_schema, quoted=True),
            ),
            column_mapping=cols,
            dialect="duckdb",
        )

        base_schema = dataset.table(tbl_name).to_ibis().schema()
        dlt_cols = discovered_schema.tables.get(tbl_name, {}).get("columns", {})
        patched_schema = ibis.schema({
            col_name: (
                dt.Timestamp(timezone="UTC", nullable=dtype.nullable)
                if dlt_cols.get(col_name, {}).get("data_type") == "timestamp"
                and dlt_cols.get(col_name, {}).get("timezone") is not False
                else dtype
            )
            for col_name, dtype in base_schema.items()
        })
        tables[tbl_name] = ibis.table(
            patched_schema, name=tbl_name, database=normalized_schema
        )

    if not tables:
        raise ValueError(
            f"Source {getattr(source, 'name', source)!r} registered no tables with static column hints."
        )

    return tables


def _drop_conflicting_relation(
    con: duckdb.DuckDBPyConnection,
    db_schema: str,
    name: str,
    materialized: Literal["view", "table"],
) -> None:
    """Drop an existing relation if its kind (table vs view) conflicts with `materialized`."""
    escaped_schema = db_schema.replace('"', '""')
    escaped_name = name.replace('"', '""')
    qualified = f'"{escaped_schema}"."{escaped_name}"'
    if materialized == "view":
        exists = con.execute(
            "SELECT 1 FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = ? AND table_name = ?",
            [db_schema, name],
        ).fetchone()
        if exists:
            con.execute(f"DROP TABLE {qualified}")
    else:
        exists = con.execute(
            "SELECT 1 FROM duckdb_views() WHERE database_name = current_database() AND schema_name = ? AND view_name = ?",
            [db_schema, name],
        ).fetchone()
        if exists:
            con.execute(f"DROP VIEW {qualified}")


def _extract_column_lineage(
    expr: ibis.Table, sql_str: str
) -> dict[str, list[tuple[str, str, str]]]:
    """Infer upstream (schema, table, column) dependencies per output column using sqlglot."""
    lineage_map: dict[str, list[tuple[str, str, str]]] = {}
    for out_col in expr.columns:
        try:
            node = lineage(out_col, sql_str, schema=_sqlglot_schema, dialect="duckdb")
        except SqlglotError as exc:
            logger.warning(
                "Could not extract sqlglot lineage for column '%s': %s", out_col, exc
            )
            lineage_map[out_col] = []
            continue
        leaves: set[tuple[str, str, str]] = set()
        for sub in node.walk():
            if isinstance(sub.source, exp.Table) and sub.source.db and sub.source.name:
                src_col = exp.to_column(sub.name, dialect="duckdb").name
                leaves.add((sub.source.db, sub.source.name, src_col))
        lineage_map[out_col] = sorted(leaves)
    return lineage_map


def _validate_and_register_ddl(
    name: str,
    db_schema: str,
    materialized: Literal["view", "table"],
    sql_str: str,
) -> None:
    """Dry-run CREATE VIEW/TABLE in in-memory DuckDB and register schema for downstream models."""
    validator_con = _get_validator_connection()
    escaped_schema = db_schema.replace('"', '""')
    escaped_name = name.replace('"', '""')
    validator_con.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"')
    _drop_conflicting_relation(validator_con, db_schema, name, materialized)
    kind_kw = "VIEW" if materialized == "view" else "TABLE"
    validator_con.execute(
        f'CREATE OR REPLACE {kind_kw} "{escaped_schema}"."{escaped_name}" AS {sql_str}'
    )
    described = validator_con.sql(
        f'DESCRIBE "{escaped_schema}"."{escaped_name}"'
    ).fetchall()
    _sqlglot_schema.add_table(
        exp.Table(
            this=exp.to_identifier(name, quoted=True),
            db=exp.to_identifier(db_schema, quoted=True),
        ),
        column_mapping={row[0]: row[1] for row in described},
        dialect="duckdb",
    )


def model(
    *,
    db_schema: str = "marts",
    materialized: Literal["view", "table"] = "view",
    unique: Sequence[str] = (),
    not_null: Sequence[str] = (),
    columns: Mapping[str, str] | None = None,
    description: str | None = None,
) -> Callable[[Callable[[], ibis.Table]], ModelDefinition]:
    """Register and compile-time validate an Ibis transformation model.

    Validates expression types via Ibis, verifies declared constraint/documented columns exist,
    extracts upstream table and column lineage, and dry-runs DDL in an in-memory DuckDB binder.
    """
    if materialized not in ("view", "table"):
        raise ValueError(
            f"Invalid materialized={materialized!r}; expected 'view' or 'table'."
        )

    def decorator(fn: Callable[[], ibis.Table]) -> ModelDefinition:
        if any(m.db_schema == db_schema and m.name == fn.__name__ for m in _models):
            raise ValueError(
                f"Model '{db_schema}.{fn.__name__}' is already registered."
            )

        expr = fn()
        if not isinstance(expr, ibis.Table):
            raise TypeError(
                f"Model '{fn.__name__}' must return an ibis.Table, got {type(expr).__name__}."
            )

        ibis_schema = expr.schema()
        col_names = set(ibis_schema.names)
        col_docs = dict(columns or {})
        unique_cols = tuple(dict.fromkeys(unique))
        not_null_cols = tuple(dict.fromkeys(not_null))

        for label, cols_to_check in (
            ("unique", unique_cols),
            ("not_null", not_null_cols),
            ("columns", col_docs.keys()),
        ):
            unknown = [col for col in cols_to_check if col not in col_names]
            if unknown:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' references unknown {label} column(s) {unknown}; "
                    f"available columns: {list(ibis_schema.names)}"
                )

        sql_str = ibis.to_sql(expr, dialect="duckdb")
        deps = tuple(
            sorted({
                (node.namespace.database, node.name)
                for node in expr.op().find((UnboundTable, DatabaseTable))
                if node.namespace.database
            })
        )
        col_lineage = _extract_column_lineage(expr, sql_str)
        _validate_and_register_ddl(fn.__name__, db_schema, materialized, sql_str)

        resolved_description = (
            description if description is not None else (inspect.getdoc(fn) or "")
        )
        definition = ModelDefinition(
            name=fn.__name__,
            db_schema=db_schema,
            materialized=materialized,
            description=resolved_description,
            expr=expr,
            sql=sql_str,
            ibis_schema=ibis_schema,
            deps=deps,
            column_lineage=col_lineage,
            unique=unique_cols,
            not_null=not_null_cols,
            columns=col_docs,
        )
        _models.append(definition)
        return definition

    return decorator


def materialize_model(
    con: duckdb.DuckDBPyConnection, model_def: ModelDefinition
) -> MaterializationStats:
    """Materialize a model into DuckDB/DuckLake in one transaction and run check aggregations."""
    escaped_schema = model_def.db_schema.replace('"', '""')
    escaped_name = model_def.name.replace('"', '""')
    qualified_name = f'"{escaped_schema}"."{escaped_name}"'
    kind_kw = "VIEW" if model_def.materialized == "view" else "TABLE"

    con.begin()
    try:
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"')
        _drop_conflicting_relation(
            con, model_def.db_schema, model_def.name, model_def.materialized
        )
        con.execute(f"CREATE OR REPLACE {kind_kw} {qualified_name} AS {model_def.sql}")

        if model_def.description:
            escaped_doc = model_def.description.replace("'", "''")
            con.execute(f"COMMENT ON {kind_kw} {qualified_name} IS '{escaped_doc}'")
        if model_def.materialized == "table" and model_def.columns:
            for col_name, col_doc in model_def.columns.items():
                escaped_col = col_name.replace('"', '""')
                escaped_col_doc = col_doc.replace("'", "''")
                con.execute(
                    f"COMMENT ON COLUMN {qualified_name}.\"{escaped_col}\" IS '{escaped_col_doc}'"
                )
        con.commit()
    except Exception:
        con.rollback()
        raise

    not_null_cols = list(model_def.not_null)
    unique_cols = list(model_def.unique)
    escaped_not_null = [col.replace('"', '""') for col in not_null_cols]
    escaped_unique = [col.replace('"', '""') for col in unique_cols]
    select_exprs = [
        "count(*)",
        *[f'count(*) FILTER (WHERE "{col}" IS NULL)' for col in escaped_not_null],
        *[f'count("{col}") - count(DISTINCT "{col}")' for col in escaped_unique],
    ]

    counts = con.sql(
        f"SELECT {', '.join(select_exprs)} FROM {qualified_name}"
    ).fetchone()
    if counts is None:
        raise RuntimeError(f"Check aggregation returned no rows for {qualified_name}.")

    not_null_offset = 1
    unique_offset = not_null_offset + len(not_null_cols)
    return MaterializationStats(
        row_count=int(counts[0]),
        null_counts={
            col: int(val)
            for col, val in zip(not_null_cols, counts[not_null_offset:unique_offset])
        },
        duplicate_counts={
            col: int(val) for col, val in zip(unique_cols, counts[unique_offset:])
        },
    )
