import contextlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb
import ibis

from transformation.engine.compiler import ModelDefinition
from transformation.engine.sql import (
    SCD2_META_COLS,
    apply_comments,
    build_add_column_asts,
    build_delete_insert_asts,
    build_merge_ast,
    build_scd2_asts,
    build_scd2_initial_sql,
    drop_conflicting_relation,
    stage_table_expr,
    uniqueness_sql_expr,
)


@dataclass(frozen=True)
class MaterializationStats:
    """Execution metrics and check counts produced by materializing a model."""

    row_count: int
    rows_affected: int | None
    null_counts: dict[str, int]
    duplicate_counts: dict[tuple[str, ...], int]
    rolled_back: bool = False


def _evaluate_checks(
    con: duckdb.DuckDBPyConnection,
    model_def: ModelDefinition,
    qualified_name: str,
) -> tuple[int, dict[str, int], dict[tuple[str, ...], int]]:
    """Run single-pass row count, not_null, and unique/primary-key check aggregations."""
    not_null_cols = list(model_def.not_null)
    unique_keys = list(model_def.unique_keys)
    escaped_not_null = [col.replace('"', '""') for col in not_null_cols]
    active_only = model_def.materialized == "scd2"

    select_exprs = [
        "count(*)",
        *[f'count(*) FILTER (WHERE "{col}" IS NULL)' for col in escaped_not_null],
        *[
            uniqueness_sql_expr(key_tuple, active_only=active_only)
            for key_tuple in unique_keys
        ],
    ]
    rows = con.execute(
        f"SELECT {', '.join(select_exprs)} FROM {qualified_name}"
    ).fetchall()
    if not rows:
        raise RuntimeError(f"Check aggregation returned no rows for {qualified_name}.")
    counts = rows[0]

    not_null_offset = 1
    unique_offset = not_null_offset + len(not_null_cols)
    return (
        int(counts[0]),
        {
            col: int(val)
            for col, val in zip(not_null_cols, counts[not_null_offset:unique_offset])
        },
        {
            key_tuple: int(val)
            for key_tuple, val in zip(unique_keys, counts[unique_offset:])
        },
    )


def _stage_incoming_batch(
    con: duckdb.DuckDBPyConnection,
    filtered_expr: ibis.Table,
    primary_key: tuple[str, ...],
    qualified_name: str,
) -> None:
    """Materialize filtered source rows into a temp table and verify incoming PK uniqueness."""
    stage_sql = ibis.to_sql(filtered_expr, dialect="duckdb")
    con.execute(f'CREATE OR REPLACE TEMP TABLE "_orca_stage" AS {stage_sql}')
    if primary_key:
        dup_sql = uniqueness_sql_expr(primary_key, active_only=False)
        dup_count = con.execute(
            f'SELECT {dup_sql} FROM "temp"."main"."_orca_stage"'
        ).fetchall()[0][0]
        if int(dup_count) > 0:
            raise ValueError(
                f"Incoming batch for {qualified_name} contains {int(dup_count)} duplicate primary_key rows."
            )


def _sync_missing_columns(
    con: duckdb.DuckDBPyConnection,
    model_def: ModelDefinition,
    existing_cols: Sequence[str],
) -> None:
    """Emit nullable-safe ALTER TABLE ADD COLUMN statements for newly added columns."""
    existing_set = set(existing_cols)
    missing = [
        (col_name, model_def.ibis_schema[col_name])
        for col_name in model_def.user_columns
        if col_name not in existing_set
    ]
    for alter_ast in build_add_column_asts(
        model_def.db_schema, model_def.name, missing
    ):
        con.execute(alter_ast.sql("duckdb"))


def _coerce_window_bound(bound: Any, is_date_col: bool) -> Any:
    """Coerce datetime partition bounds to date when incremental_key is a DATE column."""
    if is_date_col and isinstance(bound, datetime):
        return bound.date()
    return bound


def _resolve_incremental_window(
    con: duckdb.DuckDBPyConnection,
    model_def: ModelDefinition,
    qualified_name: str,
    existing_col_names: Sequence[str],
    window: tuple[Any, Any] | None,
) -> tuple[ibis.Table, Any | None, Any | None]:
    """Resolve lower/upper bounds and apply an Ibis filter for delta runs."""
    lower_bound: Any | None = None
    upper_bound: Any | None = None
    inc_key = model_def.incremental_key

    if window is not None and inc_key:
        is_date_col = model_def.ibis_schema[inc_key].is_date()
        lower_bound = _coerce_window_bound(window[0], is_date_col)
        upper_bound = _coerce_window_bound(window[1], is_date_col)
    elif inc_key and inc_key in existing_col_names:
        escaped_key = inc_key.replace('"', '""')
        max_wm = con.execute(
            f'SELECT max("{escaped_key}") FROM {qualified_name}'
        ).fetchall()[0][0]
        if max_wm is not None:
            lower_bound = max_wm - model_def.lookback if model_def.lookback else max_wm

    filtered_expr = model_def.expr
    if inc_key and lower_bound is not None:
        filtered_expr = filtered_expr.filter(filtered_expr[inc_key] >= lower_bound)
    if inc_key and upper_bound is not None:
        filtered_expr = filtered_expr.filter(filtered_expr[inc_key] < upper_bound)

    return filtered_expr, lower_bound, upper_bound


def materialize_model(
    con: duckdb.DuckDBPyConnection,
    model_def: ModelDefinition,
    *,
    full_refresh: bool = False,
    window: tuple[Any, Any] | None = None,
) -> MaterializationStats:
    """Materialize a model into DuckDB/DuckLake atomically and evaluate checks pre-commit."""
    if (
        model_def.materialized == "scd2"
        and model_def.scd2_mode == "snapshot"
        and window is not None
    ):
        raise ValueError(
            f"Model '{model_def.db_schema}.{model_def.name}' with scd2_mode='snapshot' cannot run with an incremental window."
        )

    escaped_schema = model_def.db_schema.replace('"', '""')
    escaped_name = model_def.name.replace('"', '""')
    qualified_name = f'"{escaped_schema}"."{escaped_name}"'

    uses_stage = False
    con.begin()
    try:
        tx_ts = con.execute("SELECT now()").fetchall()[0][0]
        table_exists = bool(
            con.execute(
                "SELECT 1 FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = ? AND table_name = ?",
                [model_def.db_schema, model_def.name],
            ).fetchall()
        )

        is_delta = (
            model_def.materialized in ("incremental", "scd2")
            and table_exists
            and not full_refresh
        )

        existing_col_names: list[str] = []
        filtered_expr = model_def.expr
        lower_bound: Any | None = None
        upper_bound: Any | None = None

        if is_delta:
            existing_col_names = [
                row[0] for row in con.execute(f"DESCRIBE {qualified_name}").fetchall()
            ]
            has_scd2_cols = set(SCD2_META_COLS).issubset(existing_col_names)
            if model_def.materialized == "scd2" and not has_scd2_cols:
                raise ValueError(
                    f"Table {qualified_name} is missing SCD2 columns {SCD2_META_COLS}; re-run with full_refresh=True."
                )
            if model_def.materialized == "incremental" and any(
                col in existing_col_names and col not in model_def.ibis_schema.names
                for col in SCD2_META_COLS
            ):
                raise ValueError(
                    f"Table {qualified_name} contains SCD2 columns; re-run with full_refresh=True."
                )

            filtered_expr, lower_bound, upper_bound = _resolve_incremental_window(
                con, model_def, qualified_name, existing_col_names, window
            )
            uses_stage = (
                model_def.materialized == "scd2"
                or model_def.incremental_strategy == "merge"
            )
            if uses_stage:
                _stage_incoming_batch(
                    con, filtered_expr, model_def.primary_key, qualified_name
                )

        rows_affected: int | None = None
        if not is_delta:
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"')
            drop_conflicting_relation(
                con, model_def.db_schema, model_def.name, model_def.materialized
            )
            kind_kw = "VIEW" if model_def.materialized == "view" else "TABLE"
            ddl_sql = (
                build_scd2_initial_sql(
                    model_def.expr,
                    model_def.user_columns,
                    valid_from_col=model_def.valid_from_col,
                    tx_ts=tx_ts,
                )
                if model_def.materialized == "scd2"
                else model_def.sql
            )
            con.execute(f"CREATE OR REPLACE {kind_kw} {qualified_name} AS {ddl_sql}")
        elif model_def.materialized == "incremental":
            _sync_missing_columns(con, model_def, existing_col_names)
            if model_def.incremental_strategy == "merge":
                merge_ast = build_merge_ast(
                    model_def.db_schema,
                    model_def.name,
                    stage_table_expr(),
                    model_def.user_columns,
                    model_def.primary_key,
                )
                merge_rows = con.execute(merge_ast.sql("duckdb")).fetchall()
                rows_affected = int(merge_rows[0][0]) if merge_rows else 0
            else:
                assert model_def.incremental_key is not None
                delete_ast, insert_ast = build_delete_insert_asts(
                    model_def.db_schema,
                    model_def.name,
                    filtered_expr,
                    model_def.user_columns,
                    model_def.incremental_key,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
                if delete_ast is not None:
                    con.execute(delete_ast.sql("duckdb"))
                ins_rows = con.execute(insert_ast.sql("duckdb")).fetchall()
                rows_affected = int(ins_rows[0][0]) if ins_rows else 0
        else:
            _sync_missing_columns(con, model_def, existing_col_names)
            scd2_stmts = build_scd2_asts(
                model_def.db_schema,
                model_def.name,
                stage_table_expr(),
                model_def.user_columns,
                model_def.primary_key,
                model_def.tracked_columns,
                scd2_mode=model_def.scd2_mode,
                valid_from_col=model_def.valid_from_col,
                tx_ts=tx_ts,
            )
            rows_affected = 0
            for stmt_ast in scd2_stmts:
                res_rows = con.execute(stmt_ast.sql("duckdb")).fetchall()
                if res_rows:
                    rows_affected += int(res_rows[0][0])

        apply_comments(
            con,
            qualified_name,
            model_def.materialized,
            model_def.description,
            model_def.columns,
        )
        row_count, null_counts, duplicate_counts = _evaluate_checks(
            con, model_def, qualified_name
        )
        if not is_delta and model_def.materialized != "view":
            rows_affected = row_count

        checks_failed = any(v > 0 for v in null_counts.values()) or any(
            v > 0 for v in duplicate_counts.values()
        )
        if checks_failed:
            con.rollback()
            return MaterializationStats(
                row_count=row_count,
                rows_affected=rows_affected,
                null_counts=null_counts,
                duplicate_counts=duplicate_counts,
                rolled_back=True,
            )

        con.commit()
        return MaterializationStats(
            row_count=row_count,
            rows_affected=rows_affected,
            null_counts=null_counts,
            duplicate_counts=duplicate_counts,
            rolled_back=False,
        )
    except Exception:
        con.rollback()
        raise
    finally:
        if uses_stage:
            with contextlib.suppress(duckdb.Error):
                con.execute('DROP TABLE IF EXISTS "temp"."main"."_orca_stage"')
