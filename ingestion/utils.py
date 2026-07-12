# ruff: noqa: E402
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load env variables from root .env file
load_dotenv(PROJECT_ROOT / ".env")

import dlt
from dlt.destinations.impl.ducklake.configuration import DuckLakeCredentials


def create_pipeline(pipeline_name: str, dataset_name: str = "raw") -> dlt.Pipeline:
    """Helper to initialize a dlt pipeline with DuckDB DuckLake `raw` destination."""
    credentials = DuckLakeCredentials(
        ducklake_name="orca",
        catalog=f"duckdb:///{PROJECT_ROOT}/storage/orca.ducklake",
        storage="file:storage/orca.ducklake.files",
    )

    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination=dlt.destinations.ducklake(
            credentials=credentials,
            override_data_path=True,
        ),
        dataset_name=dataset_name,
    )
