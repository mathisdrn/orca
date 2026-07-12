import logging
import os
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetSpec,
    Definitions,
    in_process_executor,
)
from dagster_dbt import DbtCliResource, DbtProject
from dagster_dbt import dbt_assets as dbt_assets_decorator
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from ingestion.hackernews import hackernews_source
from ingestion.utils import create_pipeline

hn_pipeline = create_pipeline("hackernews_ingestion")

# Prevent double logging by clearing the default console handler added by dlt
logging.getLogger("dlt").handlers.clear()


class CustomDagsterDltTranslator(DagsterDltTranslator):
    def get_asset_spec(self, data: DltResourceTranslatorData) -> AssetSpec:
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


# Define DLT assets
@dlt_assets(
    dlt_source=hackernews_source(),
    dlt_pipeline=hn_pipeline,
    name="hackernews",
    group_name="ingestion",
    dagster_dlt_translator=CustomDagsterDltTranslator(),
)
def hackernews_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


# Configure dbt project using the DbtProject helper
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = PROJECT_ROOT / "transformation"
dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()

# Ensure dbt subprocess resolves the DuckLake catalog by absolute path,
# regardless of the working directory it runs from.
_catalog = f"{PROJECT_ROOT / 'storage' / 'orca.ducklake'}"
os.environ.setdefault("DBT_DUCKDB_PATH", f"ducklake:{_catalog}")
os.environ.setdefault("DBT_DUCKDB_DATA_PATH", f"{_catalog}.files/")


# Define dbt assets dynamically from manifest
@dbt_assets_decorator(manifest=dbt_project.manifest_path)
def dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


defs = Definitions(
    assets=[
        hackernews_assets,
        dbt_assets,
    ],
    resources={
        "dlt": DagsterDltResource(),
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
    executor=in_process_executor,  # to avoid DuckDB concurrent access errors
)
