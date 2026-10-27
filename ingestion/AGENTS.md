# AGENTS.md - ingestion/

This directory contains **dlt** ingestion pipelines that extract data from source APIs, database or files and load them into the `raw` schema of DuckLake using DuckDB.

## Directory Structure
- `.dlt/`: dlt configuration and cache.
- `<source>.py`: Data source and resource implementation (e.g., `hackernews.py`).
- `run_<source>.py`: Standalone pipeline execution entrypoints (e.g., `run_hackernews.py`).
- `utils.py`: Shared pipeline initialization helpers.

## Conventions
- Use Python code instead of new dlt components (`.yaml`).
- Use `create_pipeline` from `utils.py` which loads environment variables and target DuckLake storage.
- Use a logger to track pipeline execution using `logger = logging.getLogger(__name__)`