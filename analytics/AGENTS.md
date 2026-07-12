# AGENTS.md - analytics/

This directory contains data analytics code for Orca data warehouse.

## SQL best practices
- Always query from `marts.*` tables; avoid querying raw or staging.
- Prefer explicit `SELECT` lists over `SELECT *`.

## Malloy
- use `malloy-cli` to interact with the semantic model.
- to compile models use: malloy-cli compile analytics/model.malloy --config analytics/malloy-config.json
