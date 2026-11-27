# AGENTS.md - orchestration/

This directory contains Dagster orchestration for the Orca data warehouse:
- `resources.py`: `DuckLakeResource` managing DuckDB/DuckLake connections.
- `assets.py`: `CustomDagsterDltTranslator`, `hackernews_assets`, `ModelRunConfig`, and `build_model_asset`.
- `definitions.py`: Top-level `defs` wiring ingestion, transformation models, and resources.

Commands:
- List Dagster assets using `uv run dg list defs`.
- Execute the data warehouse using `uv run dg launch --assets "*"`.