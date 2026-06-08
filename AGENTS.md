# AGENTS.md

## Overview

This project is the official development repository for **Orca**.
**Orca** is a template and set of patterns helping data team quickly setup an agentic-ready data-warehouse.

This project contains:
- `orchestration/`: Dagster orchestration.
- `ingestion/`: dlt pipelines.
- `transformation/`: dbt pipelines.
- `analysis/`: dashboards, EDA and machine learning.

It uses:
- `data/db.duckdb`: Local DuckDB database (git-ignored)
- `uv`: Python 3.13 environment (setup with `uv sync`)
- `ruff`: Python linter and formatter (use `ruff check && ruff format`)

## Architecture overview

- Data warehouse layers: `a_raw.*`, `b_staging.*`, `c_marts.*`
- Tables and columns names are in `snake_case` (e.g. `a_raw.users`)
- **Dagster** controls the execution, triggering dlt pipelines and dbt transformations sequentially.
- **dlt** extracts data and loads it into `a_raw` DuckDB schema. It handles `snake_case` formatting and schema evolution natively.
- **dbt** reads the raw schema, performs semantic renaming and explicit type casting in a staging layer, then applies business logic in downstream models.