from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

import duckdb
import ibis
from ibis.backends.sql.compilers.duckdb import compiler as duckdb_compiler
from ibis.backends.sql.datatypes import DuckDBType
from ibis.expr import datatypes as dt
from sqlglot import exp

SCD2_VALID_FROM = "valid_from"
SCD2_VALID_TO = "valid_to"
SCD2_IS_CURRENT = "is_current"
SCD2_META_COLS = (SCD2_VALID_FROM, SCD2_VALID_TO, SCD2_IS_CURRENT)


def stage_table_expr() -> exp.Table:
    """Return the sqlglot table reference for the session staging table."""
    return exp.Table(
        this=exp.to_identifier("_orca_stage", quoted=True),
        db=exp.to_identifier("main", quoted=True),
        catalog=exp.to_identifier("temp", quoted=True),
        alias=exp.TableAlias(this=exp.to_identifier("src", quoted=True)),
    )


def _timestamptz_type() -> exp.DataType:
    """Return the DuckDB TIMESTAMPTZ sqlglot DataType."""
    return exp.DataType.build("TIMESTAMPTZ", dialect="duckdb")


def _timestamp_literal_ast(value: datetime) -> exp.Cast:
    """Build a DuckDB TIMESTAMPTZ literal cast AST from a Python datetime."""
    return exp.Cast(
        this=exp.Literal.string(value.isoformat()),
        to=_timestamptz_type(),
    )


def build_add_column_asts(
    db_schema: str,
    name: str,
    missing_cols: Sequence[tuple[str, dt.DataType]],
) -> list[exp.Alter]:
    """Build nullable-safe ALTER TABLE ... ADD COLUMN ASTs for additive schema evolution."""
    target = exp.table_(name, db=db_schema, quoted=True)
    return [
        exp.Alter(
            this=target,
            kind="TABLE",
            actions=[
                exp.ColumnDef(
                    this=exp.to_identifier(col_name, quoted=True),
                    kind=DuckDBType.from_ibis(dtype.copy(nullable=True)),
                )
            ],
        )
        for col_name, dtype in missing_cols
    ]


def build_merge_ast(
    db_schema: str,
    name: str,
    stage_table: exp.Table,
    cols: Sequence[str],
    primary_key: Sequence[str],
) -> exp.Merge:
    """Build an explicit-column-list MERGE INTO AST for incremental upserts."""
    target = exp.Table(
        this=exp.to_identifier(name, quoted=True),
        db=exp.to_identifier(db_schema, quoted=True),
        alias=exp.TableAlias(this=exp.to_identifier("tgt", quoted=True)),
    )
    on_expr = exp.and_(
        *(
            exp.column(key, table="tgt", quoted=True).eq(
                exp.column(key, table="src", quoted=True)
            )
            for key in primary_key
        )
    )
    key_set = set(primary_key)
    non_key_cols = [col for col in cols if col not in key_set]

    when_clauses: list[exp.When] = []
    if non_key_cols:
        when_clauses.append(
            exp.When(
                matched=True,
                then=exp.Update(
                    expressions=[
                        exp.column(col, quoted=True).eq(
                            exp.column(col, table="src", quoted=True)
                        )
                        for col in non_key_cols
                    ]
                ),
            )
        )

    when_clauses.append(
        exp.When(
            matched=False,
            then=exp.Insert(
                this=exp.Schema(
                    expressions=[exp.to_identifier(col, quoted=True) for col in cols]
                ),
                expression=exp.Tuple(
                    expressions=[
                        exp.column(col, table="src", quoted=True) for col in cols
                    ]
                ),
            ),
        )
    )

    return exp.Merge(
        this=target,
        using=stage_table,
        on=on_expr,
        whens=exp.Whens(expressions=when_clauses),
    )


def build_delete_insert_asts(
    db_schema: str,
    name: str,
    filtered_expr: ibis.Table,
    cols: Sequence[str],
    incremental_key: str,
    *,
    lower_bound: Any | None,
    upper_bound: Any | None,
) -> tuple[exp.Delete | None, exp.Insert]:
    """Build DELETE + explicit-column INSERT ASTs for window or watermark overwrites."""
    target = exp.table_(name, db=db_schema, quoted=True)
    delete_ast: exp.Delete | None = None

    if lower_bound is not None or upper_bound is not None:
        key_tbl = ibis.table(
            {incremental_key: filtered_expr.schema()[incremental_key]},
            name=name,
            database=db_schema,
        )
        preds = []
        if lower_bound is not None:
            preds.append(key_tbl[incremental_key] >= lower_bound)
        if upper_bound is not None:
            preds.append(key_tbl[incremental_key] < upper_bound)
        where_expr = duckdb_compiler.to_sqlglot(key_tbl.filter(*preds)).args["where"]
        where_expr = where_expr.transform(
            lambda node: (
                exp.column(node.name, quoted=True)
                if isinstance(node, exp.Column)
                else node
            )
        )
        delete_ast = exp.Delete(this=target, where=where_expr)

    insert_ast = exp.Insert(
        this=exp.Schema(
            this=target,
            expressions=[exp.to_identifier(col, quoted=True) for col in cols],
        ),
        expression=duckdb_compiler.to_sqlglot(filtered_expr.select(*cols)),
    )
    return delete_ast, insert_ast


def build_scd2_initial_sql(
    expr: ibis.Table,
    user_cols: Sequence[str],
    *,
    valid_from_col: str | None,
    tx_ts: datetime,
) -> str:
    """Compile the initial SCD Type 2 SELECT query with validity metadata columns."""
    ts_type = dt.Timestamp(timezone="UTC")
    valid_from_expr = (
        expr[valid_from_col].cast(ts_type)
        if valid_from_col
        else ibis.literal(tx_ts, type=ts_type)
    )
    scd2_expr = expr.select(
        *user_cols,
        **{
            SCD2_VALID_FROM: valid_from_expr,
            SCD2_VALID_TO: ibis.null(ts_type),
            SCD2_IS_CURRENT: ibis.literal(True),
        },
    )
    return ibis.to_sql(scd2_expr, dialect="duckdb")


def build_scd2_asts(
    db_schema: str,
    name: str,
    stage_table: exp.Table,
    user_cols: Sequence[str],
    primary_key: Sequence[str],
    tracked_columns: Sequence[str],
    *,
    scd2_mode: Literal["changes", "snapshot"],
    valid_from_col: str | None,
    tx_ts: datetime,
) -> list[exp.Expression]:
    """Build transactional SCD Type 2 DML ASTs for DuckDB/DuckLake."""
    target = exp.Table(
        this=exp.to_identifier(name, quoted=True),
        db=exp.to_identifier(db_schema, quoted=True),
        alias=exp.TableAlias(this=exp.to_identifier("tgt", quoted=True)),
    )
    tx_ts_ast = _timestamp_literal_ast(tx_ts)
    src_ts_ast = (
        exp.Cast(
            this=exp.column(valid_from_col, table="src", quoted=True),
            to=_timestamptz_type(),
        )
        if valid_from_col
        else tx_ts_ast
    )

    pk_match = [
        exp.column(key, table="tgt", quoted=True).eq(
            exp.column(key, table="src", quoted=True)
        )
        for key in primary_key
    ]
    on_expr = exp.and_(
        *pk_match,
        exp.column(SCD2_IS_CURRENT, table="tgt", quoted=True).eq(exp.true()),
    )
    diff_cond = exp.or_(
        *(
            exp.NullSafeNEQ(
                this=exp.column(col, table="tgt", quoted=True),
                expression=exp.column(col, table="src", quoted=True),
            )
            for col in tracked_columns
        )
    )

    all_cols = [*user_cols, *SCD2_META_COLS]
    merge_ast = exp.Merge(
        this=target,
        using=stage_table,
        on=on_expr,
        whens=exp.Whens(
            expressions=[
                exp.When(
                    matched=True,
                    condition=diff_cond,
                    then=exp.Update(
                        expressions=[
                            exp.column(SCD2_VALID_TO, quoted=True).eq(src_ts_ast),
                            exp.column(SCD2_IS_CURRENT, quoted=True).eq(exp.false()),
                        ]
                    ),
                ),
                exp.When(
                    matched=False,
                    then=exp.Insert(
                        this=exp.Schema(
                            expressions=[
                                exp.to_identifier(col, quoted=True) for col in all_cols
                            ]
                        ),
                        expression=exp.Tuple(
                            expressions=[
                                *(
                                    exp.column(col, table="src", quoted=True)
                                    for col in user_cols
                                ),
                                src_ts_ast,
                                exp.Cast(this=exp.Null(), to=_timestamptz_type()),
                                exp.true(),
                            ]
                        ),
                    ),
                ),
            ]
        ),
    )

    exists_subquery = exp.Select(
        expressions=[exp.Literal.number(1)],
        from_=exp.From(
            this=exp.Table(
                this=exp.to_identifier(name, quoted=True),
                db=exp.to_identifier(db_schema, quoted=True),
                alias=exp.TableAlias(this=exp.to_identifier("tgt", quoted=True)),
            )
        ),
        where=exp.Where(this=on_expr),
    )
    insert_select = exp.Select(
        expressions=[
            *(exp.column(col, table="src", quoted=True) for col in user_cols),
            src_ts_ast,
            exp.Cast(this=exp.Null(), to=_timestamptz_type()),
            exp.true(),
        ],
        from_=exp.From(this=stage_table),
        where=exp.Where(this=exp.Not(this=exp.Exists(this=exists_subquery))),
    )
    insert_ast = exp.Insert(
        this=exp.Schema(
            this=exp.table_(name, db=db_schema, quoted=True),
            expressions=[exp.to_identifier(col, quoted=True) for col in all_cols],
        ),
        expression=insert_select,
    )

    stmts: list[exp.Expression] = [merge_ast]
    if scd2_mode == "snapshot":
        # DuckLake MERGE INTO currently supports a single UPDATE action, so snapshot
        # expiration of missing keys runs as a separate UPDATE inside the same transaction.
        src_exists = exp.Select(
            expressions=[exp.Literal.number(1)],
            from_=exp.From(this=stage_table),
            where=exp.Where(this=exp.and_(*pk_match)),
        )
        stmts.append(
            exp.Update(
                this=target,
                expressions=[
                    exp.column(SCD2_VALID_TO, quoted=True).eq(tx_ts_ast),
                    exp.column(SCD2_IS_CURRENT, quoted=True).eq(exp.false()),
                ],
                where=exp.Where(
                    this=exp.and_(
                        exp.column(SCD2_IS_CURRENT, table="tgt", quoted=True).eq(
                            exp.true()
                        ),
                        exp.Not(this=exp.Exists(this=src_exists)),
                    )
                ),
            )
        )
    stmts.append(insert_ast)
    return stmts


def drop_conflicting_relation(
    con: duckdb.DuckDBPyConnection,
    db_schema: str,
    name: str,
    materialized: str,
) -> None:
    """Drop an existing relation if its kind (table vs view) conflicts with `materialized`."""
    escaped_schema = db_schema.replace('"', '""')
    escaped_name = name.replace('"', '""')
    qualified = f'"{escaped_schema}"."{escaped_name}"'
    if materialized == "view":
        exists = con.execute(
            "SELECT 1 FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = ? AND table_name = ?",
            [db_schema, name],
        ).fetchall()
        if exists:
            con.execute(f"DROP TABLE {qualified}")
    else:
        exists = con.execute(
            "SELECT 1 FROM duckdb_views() WHERE database_name = current_database() AND schema_name = ? AND view_name = ?",
            [db_schema, name],
        ).fetchall()
        if exists:
            con.execute(f"DROP VIEW {qualified}")


def apply_comments(
    con: duckdb.DuckDBPyConnection,
    qualified_name: str,
    materialized: str,
    description: str,
    columns: Mapping[str, str],
) -> None:
    """Persist view/table and column comments into the DuckDB/DuckLake catalog."""
    kind_kw = "VIEW" if materialized == "view" else "TABLE"
    if description:
        escaped_doc = description.replace("'", "''")
        con.execute(f"COMMENT ON {kind_kw} {qualified_name} IS '{escaped_doc}'")
    if materialized != "view" and columns:
        for col_name, col_doc in columns.items():
            escaped_col = col_name.replace('"', '""')
            escaped_col_doc = col_doc.replace("'", "''")
            con.execute(
                f"COMMENT ON COLUMN {qualified_name}.\"{escaped_col}\" IS '{escaped_col_doc}'"
            )


def uniqueness_sql_expr(
    key_tuple: tuple[str, ...], *, active_only: bool = False
) -> str:
    """Build a DuckDB duplicate-count SQL expression for a single or composite key."""
    escaped = [col.replace('"', '""') for col in key_tuple]
    active_filter = f'"{SCD2_IS_CURRENT}" = TRUE' if active_only else ""
    if len(escaped) == 1:
        col = escaped[0]
        if active_only:
            return f'count("{col}") FILTER (WHERE {active_filter}) - count(DISTINCT "{col}") FILTER (WHERE {active_filter})'
        return f'count("{col}") - count(DISTINCT "{col}")'

    not_null_cond = " AND ".join(f'"{col}" IS NOT NULL' for col in escaped)
    cond = f"{not_null_cond} AND {active_filter}" if active_only else not_null_cond
    struct_args = ", ".join(f'"{col}" := "{col}"' for col in escaped)
    return (
        f"count(*) FILTER (WHERE {cond}) - "
        f"count(DISTINCT struct_pack({struct_args})) FILTER (WHERE {cond})"
    )
