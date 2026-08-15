# AGENTS.md - analytics/

This directory contains data analytics code for Orca data warehouse.

## SQL best practices
- Always query from `marts.*` tables; avoid querying raw or staging.
- Prefer explicit `SELECT` lists over `SELECT *`.

## Malloy
- Always use fully qualified table names in Malloy source definitions (e.g. `source: stories is orca.table('marts.stories')`) to enable automatic multi-part Dagster asset lineage resolution.
- Use `malloy-cli` to interact with the semantic model.
- Compile models using `malloy-cli compile analytics/model.malloy --config analytics/malloy-config.json`.
- Re-generate pre-compiled AST manifests using `uv run python analytics/build_manifest.py` after modifying `.malloy` models.