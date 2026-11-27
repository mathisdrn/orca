from pathlib import Path

import dagster as dg
from dagster_dlt import DagsterDltResource

from orchestration.assets import build_model_asset, hackernews_assets
from orchestration.resources import DuckLakeResource
from transformation.engine.compiler import get_models
from transformation.models import marts

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
