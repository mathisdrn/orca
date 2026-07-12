# AGENTS.md - ingestion/

This directory contains **dlt** ingestion pipelines that extract data from source APIs, database or files and load them into the `raw` schema of DuckLake using DuckDB.

## Directory Structure
- `.dlt/`: dlt configuration and cache.
- `sources/`: Data sources implementation.
- `pipelines/`: Pipeline execution entrypoints.

## Conventions
- Use `create_pipeline` from `utils.py` which loads environment variables and target DuckLake storage.
- Use a logger to track pipeline execution using `logger = logging.getLogger(__name__)`