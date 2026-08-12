# AGENTS.md - analytics/

This directory contains data analytics code for Orca data warehouse.

## SQL best practices
- Always query from `marts.*` tables; avoid querying raw or staging.
- Prefer explicit `SELECT` lists over `SELECT *`.

## Malloy
- Use `malloy-cli` to interact with the semantic model.
- Compile models using `malloy-cli compile analytics/model.malloy --config analytics/malloy-config.json`.