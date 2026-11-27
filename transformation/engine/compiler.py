import hashlib
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

from transformation.engine.sql import (
    SCD2_IS_CURRENT,
    SCD2_META_COLS,
    SCD2_VALID_FROM,
    SCD2_VALID_TO,
    build_scd2_initial_sql,
    drop_conflicting_relation,
)

logger = logging.getLogger(__name__)

MaterializationMode = Literal["view", "table", "incremental", "scd2"]
IncrementalStrategy = Literal["merge", "delete_insert"]
Scd2Mode = Literal["changes", "snapshot"]

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
    materialized: MaterializationMode
    description: str
    expr: ibis.Table
    sql: str
    ibis_schema: ibis.Schema
    deps: tuple[tuple[str, str], ...]
    column_lineage: dict[str, list[tuple[str, str, str]]]
    primary_key: tuple[str, ...]
    unique_keys: tuple[tuple[str, ...], ...]
    not_null: tuple[str, ...]
    columns: dict[str, str]
    incremental_strategy: IncrementalStrategy
    incremental_key: str | None
    lookback: timedelta | None
    scd2_mode: Scd2Mode
    tracked_columns: tuple[str, ...]
    valid_from_col: str | None
    code_version: str

    @property
    def table(self) -> ibis.Table:
        """Return an unbound Ibis table expression referencing this model."""
        return ibis.table(self.ibis_schema, name=self.name, database=self.db_schema)

    @property
    def user_columns(self) -> tuple[str, ...]:
        """Return user-defined output column names (excluding SCD2 validity metadata)."""
        if self.materialized != "scd2":
            return tuple(self.ibis_schema.names)
        return tuple(col for col in self.ibis_schema.names if col not in SCD2_META_COLS)


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
    materialized: MaterializationMode,
    ddl_sql: str,
) -> None:
    """Dry-run CREATE VIEW/TABLE in in-memory DuckDB and register schema for downstream models."""
    validator_con = _get_validator_connection()
    escaped_schema = db_schema.replace('"', '""')
    escaped_name = name.replace('"', '""')
    validator_con.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"')
    drop_conflicting_relation(validator_con, db_schema, name, materialized)
    kind_kw = "VIEW" if materialized == "view" else "TABLE"
    validator_con.execute(
        f'CREATE OR REPLACE {kind_kw} "{escaped_schema}"."{escaped_name}" AS {ddl_sql}'
    )
    described = validator_con.execute(
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


def _compute_code_version(
    sql_str: str,
    ibis_schema: ibis.Schema,
    materialized: MaterializationMode,
    primary_key: tuple[str, ...],
    incremental_strategy: IncrementalStrategy,
    incremental_key: str | None,
    lookback: timedelta | None,
    scd2_mode: Scd2Mode,
    tracked_columns: tuple[str, ...],
    valid_from_col: str | None,
) -> str:
    """Compute a deterministic short hash representing model logic and schema."""
    payload = "|".join([
        sql_str,
        repr(ibis_schema),
        materialized,
        ",".join(primary_key),
        incremental_strategy,
        incremental_key or "",
        str(lookback.total_seconds()) if lookback is not None else "",
        scd2_mode,
        ",".join(tracked_columns),
        valid_from_col or "",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def model(
    *,
    db_schema: str = "marts",
    materialized: MaterializationMode = "view",
    primary_key: str | Sequence[str] = (),
    unique: Sequence[str] = (),
    not_null: Sequence[str] = (),
    columns: Mapping[str, str] | None = None,
    description: str | None = None,
    incremental_strategy: IncrementalStrategy = "merge",
    incremental_key: str | None = None,
    lookback: timedelta | None = None,
    scd2_mode: Scd2Mode = "changes",
    tracked_columns: Sequence[str] | None = None,
    valid_from_col: str | None = None,
) -> Callable[[Callable[[], ibis.Table]], ModelDefinition]:
    """Register and compile-time validate an Ibis transformation model.

    Validates expression types via Ibis, verifies declared constraint/documented columns exist,
    extracts upstream table and column lineage, and dry-runs DDL in an in-memory DuckDB binder.
    """
    if materialized not in ("view", "table", "incremental", "scd2"):
        raise ValueError(
            f"Invalid materialized={materialized!r}; expected 'view', 'table', 'incremental', or 'scd2'."
        )
    if incremental_strategy not in ("merge", "delete_insert"):
        raise ValueError(
            f"Invalid incremental_strategy={incremental_strategy!r}; expected 'merge' or 'delete_insert'."
        )
    if scd2_mode not in ("changes", "snapshot"):
        raise ValueError(
            f"Invalid scd2_mode={scd2_mode!r}; expected 'changes' or 'snapshot'."
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

        user_schema = expr.schema()
        user_col_names = set(user_schema.names)
        col_docs = dict(columns or {})

        pk_cols = (
            (primary_key,)
            if isinstance(primary_key, str)
            else tuple(dict.fromkeys(primary_key))
        )
        unique_cols = tuple(dict.fromkeys(unique))
        not_null_cols = tuple(dict.fromkeys([*pk_cols, *not_null]))

        unique_keys_list: list[tuple[str, ...]] = [pk_cols] if pk_cols else []
        for col in unique_cols:
            if (col,) != pk_cols:
                unique_keys_list.append((col,))
        unique_keys = tuple(dict.fromkeys(unique_keys_list))

        for label, cols_to_check in (
            ("primary_key", pk_cols),
            ("unique", unique_cols),
            ("not_null", not_null),
            ("incremental_key", (incremental_key,) if incremental_key else ()),
            ("valid_from_col", (valid_from_col,) if valid_from_col else ()),
            ("tracked_columns", tracked_columns or ()),
        ):
            unknown = [col for col in cols_to_check if col not in user_col_names]
            if unknown:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' references unknown {label} column(s) {unknown}; "
                    f"available columns: {list(user_schema.names)}"
                )

        if materialized in ("view", "table") and (
            incremental_key is not None or lookback is not None
        ):
            raise ValueError(
                f"Model '{db_schema}.{fn.__name__}' with materialized={materialized!r} cannot specify incremental_key or lookback."
            )
        if materialized != "incremental" and incremental_strategy != "merge":
            raise ValueError(
                f"Model '{db_schema}.{fn.__name__}' with materialized={materialized!r} cannot specify incremental_strategy={incremental_strategy!r}."
            )
        if materialized != "scd2" and (
            tracked_columns is not None
            or valid_from_col is not None
            or scd2_mode != "changes"
        ):
            raise ValueError(
                f"Model '{db_schema}.{fn.__name__}' with materialized={materialized!r} cannot specify scd2_mode, tracked_columns, or valid_from_col."
            )

        if materialized == "incremental":
            if incremental_strategy == "merge" and not pk_cols:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' with incremental_strategy='merge' requires primary_key."
                )
            if incremental_strategy == "delete_insert" and not incremental_key:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' with incremental_strategy='delete_insert' requires incremental_key."
                )

        resolved_tracked: tuple[str, ...] = ()
        final_schema = user_schema
        if materialized == "scd2":
            if not pk_cols:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' with materialized='scd2' requires primary_key."
                )
            if scd2_mode == "snapshot" and (incremental_key or lookback):
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' with scd2_mode='snapshot' cannot use incremental_key or lookback."
                )
            reserved_hits = [col for col in SCD2_META_COLS if col in user_col_names]
            if reserved_hits:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' cannot declare reserved SCD2 columns {reserved_hits}."
                )
            if valid_from_col and not (
                user_schema[valid_from_col].is_timestamp()
                or user_schema[valid_from_col].is_date()
            ):
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' valid_from_col='{valid_from_col}' must be a temporal column, "
                    f"got {user_schema[valid_from_col]}."
                )
            if tracked_columns is not None:
                resolved_tracked = tuple(dict.fromkeys(tracked_columns))
            else:
                pk_set = set(pk_cols)
                resolved_tracked = tuple(
                    col
                    for col in user_schema.names
                    if col not in pk_set and col != valid_from_col
                )
            if not resolved_tracked:
                raise ValueError(
                    f"Model '{db_schema}.{fn.__name__}' with materialized='scd2' requires at least one tracked column."
                )
            ts_type = dt.Timestamp(timezone="UTC")
            final_schema = ibis.schema({
                **dict(user_schema.items()),
                SCD2_VALID_FROM: ts_type.copy(nullable=False),
                SCD2_VALID_TO: ts_type.copy(nullable=True),
                SCD2_IS_CURRENT: dt.Boolean(nullable=False),
            })
            not_null_cols = tuple(
                dict.fromkeys([
                    *not_null_cols,
                    *([valid_from_col] if valid_from_col else []),
                    SCD2_VALID_FROM,
                    SCD2_IS_CURRENT,
                ])
            )

        unknown_docs = [col for col in col_docs if col not in set(final_schema.names)]
        if unknown_docs:
            raise ValueError(
                f"Model '{db_schema}.{fn.__name__}' references unknown columns {unknown_docs}; "
                f"available columns: {list(final_schema.names)}"
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
        if materialized == "scd2":
            for meta_col in SCD2_META_COLS:
                col_lineage[meta_col] = []
            ddl_sql = build_scd2_initial_sql(
                expr,
                list(user_schema.names),
                valid_from_col=valid_from_col,
                tx_ts=datetime.now(UTC),
            )
        else:
            ddl_sql = sql_str

        _validate_and_register_ddl(fn.__name__, db_schema, materialized, ddl_sql)

        resolved_description = (
            description if description is not None else (inspect.getdoc(fn) or "")
        )
        code_version = _compute_code_version(
            sql_str,
            final_schema,
            materialized,
            pk_cols,
            incremental_strategy,
            incremental_key,
            lookback,
            scd2_mode,
            resolved_tracked,
            valid_from_col,
        )
        definition = ModelDefinition(
            name=fn.__name__,
            db_schema=db_schema,
            materialized=materialized,
            description=resolved_description,
            expr=expr,
            sql=sql_str,
            ibis_schema=final_schema,
            deps=deps,
            column_lineage=col_lineage,
            primary_key=pk_cols,
            unique_keys=unique_keys,
            not_null=not_null_cols,
            columns=col_docs,
            incremental_strategy=incremental_strategy,
            incremental_key=incremental_key,
            lookback=lookback,
            scd2_mode=scd2_mode,
            tracked_columns=resolved_tracked,
            valid_from_col=valid_from_col,
            code_version=code_version,
        )
        _models.append(definition)
        return definition

    return decorator
