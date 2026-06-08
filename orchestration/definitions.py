import os
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    Definitions,
    in_process_executor,
)
from dagster_dbt import DbtCliResource, DbtProject
from dagster_dbt import dbt_assets as dbt_assets_decorator
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

# 1. Programmatically align DLT_CONFIG_FOLDER before importing dlt
PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ["DLT_CONFIG_FOLDER"] = str(PROJECT_ROOT / "ingestion" / ".dlt")
os.environ["DBT_DUCKDB_PATH"] = str(PROJECT_ROOT / "data" / "db.duckdb")


from ingestion.house_price_pipeline import house_price_source  # noqa: E402
from ingestion.iris_pipeline import iris_source  # noqa: E402
from ingestion.products_pipeline import products_source  # noqa: E402
from ingestion.utils import create_pipeline  # noqa: E402

# 2. Configure dbt project using the DbtProject helper
DBT_PROJECT_DIR = PROJECT_ROOT / "transformation"
dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()

dbt_resource = DbtCliResource(project_dir=dbt_project)


# 3. Create custom translator to map dlt assets directly to the "a_raw" schema prefix
class CustomDagsterDltTranslator(DagsterDltTranslator):
    def get_asset_spec(self, data: DltResourceTranslatorData) -> AssetSpec:
        # Generate default spec and customize key and group name
        default_spec = super().get_asset_spec(data)
        return default_spec.replace_attributes(
            key=AssetKey(["a_raw", data.resource.name]),
            group_name="ingestion",
        )


# Define DLT assets using the custom translator
@dlt_assets(
    dlt_source=house_price_source(),
    dlt_pipeline=create_pipeline("house_price_ingestion"),
    name="house_prices",
    dagster_dlt_translator=CustomDagsterDltTranslator(),
)
def house_prices_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


@dlt_assets(
    dlt_source=iris_source(),
    dlt_pipeline=create_pipeline("iris_borders_ingestion"),
    name="iris_borders",
    dagster_dlt_translator=CustomDagsterDltTranslator(),
)
def iris_borders_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


@dlt_assets(
    dlt_source=products_source(),
    dlt_pipeline=create_pipeline("products_ingestion"),
    name="products",
    dagster_dlt_translator=CustomDagsterDltTranslator(),
)
def products_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


# Define dbt assets dynamically from manifest
@dbt_assets_decorator(manifest=dbt_project.manifest_path)
def orca_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


defs = Definitions(
    assets=[
        house_prices_assets,
        iris_borders_assets,
        products_assets,
        orca_dbt_assets,
    ],
    resources={
        "dlt": DagsterDltResource(),
        "dbt": dbt_resource,
    },
    executor=in_process_executor,
)
