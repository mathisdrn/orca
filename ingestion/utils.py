import os
from pathlib import Path

# Dynamically resolve project root and align DLT_CONFIG_FOLDER before importing dlt
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DLT_CONFIG_FOLDER = PROJECT_ROOT / "ingestion" / ".dlt"
os.environ["DLT_CONFIG_FOLDER"] = str(DLT_CONFIG_FOLDER)

import dlt  # noqa: E402


def create_pipeline(pipeline_name: str, dataset_name: str = "a_raw") -> dlt.Pipeline:
    """Centralized helper to initialize a dlt pipeline with robust configurations.

    This programmatically sets the DLT_CONFIG_FOLDER environment variable and
    resolves the absolute DuckDB path relative to the project root.
    """
    # Resolve DuckDB path dynamically to absolute path and set in environment variables
    db_path = PROJECT_ROOT / "data" / "db.duckdb"
    os.environ["DESTINATION__DUCKDB__CREDENTIALS__DATABASE"] = str(db_path)
    os.environ.setdefault("DESTINATION__DUCKDB__CREDENTIALS__EXTENSIONS", '["spatial"]')

    # Create and return the pipeline, letting config.toml merge credentials
    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="duckdb",
        dataset_name=dataset_name,
    )
