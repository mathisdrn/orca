import logging
from collections.abc import Iterator

import dagster as dg
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from ingestion.hackernews import hackernews_source
from ingestion.utils import create_pipeline
from orchestration.resources import DuckLakeResource
from transformation.engine.compiler import ModelDefinition
from transformation.engine.executor import MaterializationStats, materialize_model

hn_pipeline = create_pipeline("hackernews_ingestion")

# Prevent double logging by clearing the default console handler added by dlt
logging.getLogger("dlt").handlers.clear()


class CustomDagsterDltTranslator(DagsterDltTranslator):
    """Map dlt resource names and docstrings to Dagster raw AssetSpecs."""

    def get_asset_spec(self, data: DltResourceTranslatorData) -> dg.AssetSpec:
        """Customize the AssetSpec key and description for each dlt resource."""
        doc = data.resource.__doc__
        description = doc.strip().split("\n")[0].strip() if doc else None
        return (
            super()
            .get_asset_spec(data)
            .replace_attributes(
                key=["raw", data.resource.name],
                description=description,
            )
        )


@dlt_assets(
    dlt_source=hackernews_source(),
    dlt_pipeline=hn_pipeline,
    name="hackernews",
    group_name="ingestion",
    dagster_dlt_translator=CustomDagsterDltTranslator(),
)
def hackernews_assets(context: dg.AssetExecutionContext, dlt: DagsterDltResource):
    """Ingest Hacker News items incrementally into the DuckLake raw layer."""
    yield from dlt.run(context=context)


class ModelRunConfig(dg.Config):
    """Runtime execution options for physical transformation models."""

    full_refresh: bool = False


def build_model_asset(
    model_def: ModelDefinition,
    *,
    partitions_def: dg.PartitionsDefinition | None = None,
) -> dg.AssetsDefinition:
    """Create a Dagster asset and inline data quality checks for a transformation model."""
    asset_key = [model_def.db_schema, model_def.name]
    table_name = f"orca.{model_def.db_schema}.{model_def.name}"
    table_schema = dg.TableSchema(
        columns=[
            dg.TableColumn(
                name=col_name,
                type=str(dtype.copy(nullable=True)),
                description=model_def.columns.get(col_name),
                constraints=dg.TableColumnConstraints(
                    nullable=col_name not in model_def.not_null,
                    unique=(
                        model_def.materialized != "scd2"
                        and (col_name,) in model_def.unique_keys
                    ),
                ),
            )
            for col_name, dtype in model_def.ibis_schema.items()
        ]
    )
    column_lineage = dg.TableColumnLineage(
        deps_by_column={
            col_name: [
                dg.TableColumnDep(
                    asset_key=dg.AssetKey([src_db, src_tbl]),
                    column_name=src_col,
                )
                for src_db, src_tbl, src_col in deps
            ]
            for col_name, deps in model_def.column_lineage.items()
            if deps
        }
    )
    sql_markdown = dg.MetadataValue.md(f"```sql\n{model_def.sql}\n```")

    not_null_checks = [
        (col, f"not_null_{model_def.name}_{col}") for col in model_def.not_null
    ]
    unique_checks = [
        (key_tuple, f"unique_{model_def.name}_{'_'.join(key_tuple)}")
        for key_tuple in model_def.unique_keys
    ]
    check_specs = [
        *[
            dg.AssetCheckSpec(
                name=check_name,
                asset=asset_key,
                blocking=True,
                description=f"Verify {col} has no NULL values.",
            )
            for col, check_name in not_null_checks
        ],
        *[
            dg.AssetCheckSpec(
                name=check_name,
                asset=asset_key,
                blocking=True,
                description=f"Verify ({', '.join(key_tuple)}) has no duplicate values.",
            )
            for key_tuple, check_name in unique_checks
        ],
    ]

    def _emit_results(
        stats: MaterializationStats,
    ) -> Iterator[dg.MaterializeResult | dg.AssetCheckResult]:
        if not stats.rolled_back:
            mat_metadata: dict[str, object] = {
                "dagster/table_name": table_name,
                "dagster/row_count": stats.row_count,
                "dagster/column_schema": table_schema,
                "dagster/column_lineage": column_lineage,
                "sql": sql_markdown,
            }
            if stats.rows_affected is not None:
                mat_metadata["rows_affected"] = stats.rows_affected
            yield dg.MaterializeResult(metadata=mat_metadata)

        for col, check_name in not_null_checks:
            null_count = stats.null_counts[col]
            yield dg.AssetCheckResult(
                check_name=check_name,
                passed=null_count == 0,
                metadata={"null_count": null_count},
            )
        for key_tuple, check_name in unique_checks:
            dup_count = stats.duplicate_counts[key_tuple]
            yield dg.AssetCheckResult(
                check_name=check_name,
                passed=dup_count == 0,
                metadata={"duplicate_count": dup_count},
            )

    asset_decorator = dg.asset(
        key=asset_key,
        deps=[dg.AssetKey(list(dep)) for dep in model_def.deps],
        group_name=model_def.db_schema,
        kinds={"ibis", "ducklake", model_def.materialized},
        description=model_def.description,
        code_version=model_def.code_version,
        output_required=False,
        partitions_def=partitions_def,
        metadata={
            "dagster/table_name": table_name,
            "dagster/column_schema": table_schema,
            "dagster/column_lineage": column_lineage,
            "sql": sql_markdown,
        },
        check_specs=check_specs,
    )

    if model_def.materialized == "view":

        @asset_decorator
        def _view_asset(
            ducklake: DuckLakeResource,
        ) -> Iterator[dg.MaterializeResult | dg.AssetCheckResult]:
            with ducklake.connect() as con:
                stats = materialize_model(con, model_def)
            yield from _emit_results(stats)

        return _view_asset

    @asset_decorator
    def _table_asset(
        context: dg.AssetExecutionContext,
        ducklake: DuckLakeResource,
        config: ModelRunConfig,
    ) -> Iterator[dg.MaterializeResult | dg.AssetCheckResult]:
        window = None
        if isinstance(partitions_def, dg.TimeWindowPartitionsDefinition):
            if context.has_partition_key:
                window = (
                    context.partition_time_window.start,
                    context.partition_time_window.end,
                )
            elif context.has_partition_key_range:
                pkr = context.partition_key_range
                window = (
                    partitions_def.time_window_for_partition_key(pkr.start).start,
                    partitions_def.time_window_for_partition_key(pkr.end).end,
                )
        with ducklake.connect() as con:
            stats = materialize_model(
                con,
                model_def,
                full_refresh=config.full_refresh,
                window=window,
            )
        yield from _emit_results(stats)

    return _table_asset
