# AGENTS.md - Orca

Orca is a data warehouse as-code implementation built around HackerNews data.

This project contains:
- `ingestion/`: dlt pipelines for ingestion in `raw` schema
- `transformation/`: dbt pipelines for transformation in `marts` schema
- `orchestration/`: Dagster orchestrations
- `storage/`: Database storage using DuckLake lakehouse format, DuckDB as a catalog and query engine
- `semantic_model/`: Malloy semantic models
- `reporting/`: Streamlit dashboard and Malloy Publisher server
- `.github/workflows/`: Data warehouse execution. Artifacts are force-pushed to GitHub but git-ignored for local-development.
- `uv` for Python environment
- `ruff` for linter and formatter