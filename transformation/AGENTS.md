# AGENTS.md - transformation/

Typed Python/Ibis transformations compiled to DuckLake views and tables.

## Engine API & structure
- `engine/sql.py`: Pure `sqlglot` AST builders for dynamic DDL/DML (`ALTER TABLE ADD COLUMN`, `MERGE INTO`, `DELETE + INSERT`, and two-step `SCD2`) plus DuckDB relation/comment/uniqueness SQL helpers.
- `engine/compiler.py`: Domain-agnostic, Dagster-free compiler & registry (`register_dlt_source`, `@model`, `get_models`, `reset_registry`, `ModelDefinition`).
- `engine/executor.py`: Transactional DuckDB/DuckLake materialization (`materialize_model`, `MaterializationStats`) with staging, schema evolution, and pre-commit check rollback.
- `models/sources.py`: Register upstream `dlt` sources with `register_dlt_source(source, db_schema="raw")` to expose unbound `ibis.Table` contracts.
- `models/<layer>.py` (e.g., `models/marts.py`): Define models with `@model(db_schema=..., materialized=..., primary_key=..., unique=..., not_null=..., columns=...)` returning an `ibis.Table`. Chain upstream models via `<model>.table`. `orchestration/definitions.py` loads model modules explicitly via `get_models(marts)`.

## Materialization modes
- `view` (default) and `table`: Atomic single-transaction `CREATE OR REPLACE` + `COMMENT ON`.
- `incremental`: Supports `incremental_strategy="merge"` (default, requires `primary_key`) and `"delete_insert"` (requires `incremental_key`), with optional `lookback`, nullable-safe additive `ADD COLUMN`, and `full_refresh=True` via Dagster config.
- `scd2`: Tracks `valid_from`, `valid_to`, and `is_current` in `changes` or `snapshot` mode (`primary_key`, optional `tracked_columns` and `valid_from_col`).

## Conventions & verification
- Use `ibis` expressions (`from ibis import _`) instead of raw SQL or `SELECT *`.
- Give each `@model` a docstring, column descriptions in `columns={...}`, and checks via `primary_key=`, `unique=`, and `not_null=`.
- Validate types, schemas, and DDL offline with `uv run dg check defs`; run local tests with `uv run pytest`; materialize with `uv run dg launch --assets "group:marts"`.
