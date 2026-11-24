import contextlib
import logging
from collections.abc import Generator, Iterator
from pathlib import Path

import dagster as dg
import duckdb
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from ingestion.hackernews import hackernews_source
from ingestion.utils import create_pipeline
from transformation import marts
from transformation.engine import ModelDefinition, get_models, materialize_model

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


class DuckLakeResource(dg.ConfigurableResource):
    """DuckDB connection resource attached to the Orca DuckLake catalog."""

    catalog_path: str
    data_path: str

    @contextlib.contextmanager
    def connect(self) -> Generator[duckdb.DuckDBPyConnection]:
        """Open a DuckDB session attached to the configured DuckLake catalog."""
        escaped_catalog = self.catalog_path.replace("'", "''")
        escaped_data = self.data_path.replace("'", "''")
        with duckdb.connect() as con:
            con.execute("LOAD ducklake")
            con.execute(
                f"ATTACH 'ducklake:{escaped_catalog}' AS orca "
                f"(DATA_PATH '{escaped_data}', OVERRIDE_DATA_PATH true)"
            )
            con.execute("USE orca")
            yield con


def build_model_asset(model_def: ModelDefinition) -> dg.AssetsDefinition:
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
                    unique=col_name in model_def.unique,
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
        (col, f"unique_{model_def.name}_{col}") for col in model_def.unique
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
                description=f"Verify {col} has no duplicate values.",
            )
            for col, check_name in unique_checks
        ],
    ]

    @dg.asset(
        key=asset_key,
        deps=[dg.AssetKey(list(dep)) for dep in model_def.deps],
        group_name=model_def.db_schema,
        kinds={"ibis", "ducklake", model_def.materialized},
        description=model_def.description,
        metadata={
            "dagster/table_name": table_name,
            "dagster/column_schema": table_schema,
            "dagster/column_lineage": column_lineage,
            "sql": sql_markdown,
        },
        check_specs=check_specs,
    )
    def _model_asset(
        ducklake: DuckLakeResource,
    ) -> Iterator[dg.MaterializeResult | dg.AssetCheckResult]:
        with ducklake.connect() as con:
            stats = materialize_model(con, model_def)

        yield dg.MaterializeResult(
            metadata={
                "dagster/table_name": table_name,
                "dagster/row_count": stats.row_count,
                "dagster/column_schema": table_schema,
                "dagster/column_lineage": column_lineage,
                "sql": sql_markdown,
            }
        )
        for col, check_name in not_null_checks:
            null_count = stats.null_counts[col]
            yield dg.AssetCheckResult(
                check_name=check_name,
                passed=null_count == 0,
                metadata={"null_count": null_count},
            )
        for col, check_name in unique_checks:
            dup_count = stats.duplicate_counts[col]
            yield dg.AssetCheckResult(
                check_name=check_name,
                passed=dup_count == 0,
                metadata={"duplicate_count": dup_count},
            )

    return _model_asset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUCKLAKE_PATH = PROJECT_ROOT / "storage" / "orca.ducklake"

defs = dg.Definitions(
    assets=[
        hackernews_assets,
        *[build_model_asset(model_def) for model_def in get_models(marts)],
    ],
    resources={
        "dlt": DagsterDltResource(),
        "ducklake": DuckLakeResource(
            catalog_path=DUCKLAKE_PATH.as_posix(),
            data_path=f"{DUCKLAKE_PATH.as_posix()}.files/",
        ),
    },
    executor=dg.in_process_executor,  # to avoid DuckDB concurrent access errors
)
