# AGENTS.md - ingestion/

## Overview
This directory contains **dlt** (Data Load Tool) pipelines that extract data from source APIs or files and load them into the raw DuckDB database under the `a_raw` schema.

## Directory Structure
- `ingestion/`: Python pipeline scripts (e.g., `github_pipeline.py`).
- `ingestion/.dlt/`: local dlt configuration (`config.toml`) and secrets (`secrets.toml`).

## Conventions for Ingestion Pipelines

To ensure seamless local development, easy orchestration via Dagster, and robust agentic support, all dlt pipelines in Orca must follow these conventions:

### 1. Centralized Pipeline & Path Configuration
To avoid duplicate boilerplate and configuration loading issues when running via CLI or orchestrators like Dagster, always initialize your pipelines using the centralized `create_pipeline` helper function defined in `ingestion/utils.py`. This helper programmatically sets the correct `DLT_CONFIG_FOLDER` and dynamically resolves the absolute DuckDB database path relative to the project root.

```python
from ingestion.utils import create_pipeline

# Initialize the pipeline using the centralized helper
pipeline = create_pipeline(pipeline_name="my_pipeline", dataset_name="a_raw")
```

Do not manually configure `DLT_CONFIG_FOLDER` or instantiate `dlt.pipeline` with hardcoded credentials paths in individual pipeline files.

### 3. Naming Conventions & Schema Setup
- **Schema Name**: Always load into the `a_raw` dataset schema.
- **Naming Convention**: Columns and tables must be in `snake_case`. This is handled automatically by the naming convention provider in `.dlt/config.toml`.

### 4. Credential Security
- Store local development secrets (API keys, database tokens) in `ingestion/.dlt/secrets.toml`.
- Never commit `secrets.toml` to version control.
- In production, configure secrets using environment variables (e.g. `SOURCES__<SOURCE_NAME>__API_KEY`) or via your deployment environment's secret manager.
