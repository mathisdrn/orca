# AGENTS.md - transformation/

Typed Python/Ibis transformations compiled to DuckLake views and tables.

## Engine API & structure
- `sources.py`: Register upstream `dlt` sources with `register_dlt_source(source, db_schema="raw")` to expose unbound `ibis.Table` contracts.
- `<layer>.py` (e.g., `marts.py`): Define models with `@model(db_schema=..., materialized=..., unique=..., not_null=..., columns=...)` returning an `ibis.Table`. Chain upstream models via `<model>.table`.
- Keep `engine.py` free of domain-specific imports; `orchestration/definitions.py` loads model modules explicitly via `get_models(marts)`.

## Conventions & verification
- Use `ibis` expressions (`from ibis import _`) instead of raw SQL or `SELECT *`.
- Give each `@model` a docstring, column descriptions in `columns={...}`, and primary-key checks via `unique=(...,)` and `not_null=(...,)`.
- Validate types, schemas, and DDL offline with `uv run dg check defs`; materialize with `uv run dg launch --assets "group:marts"`.
