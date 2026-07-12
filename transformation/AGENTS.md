# AGENTS.md - transformation/

This directory contains dbt transformation pipelines for Orca data warehouse. `raw` contains raw data extracted by dlt. `marts` contains cleaned and structured raw data as views.

## dbt CLI
- Run commands from the `transformation/` directory: `cd transformation/ && dbt ...`.
- Always use `--threads 1` for dbt commands to prevent concurrent write lock conflicts on DuckDB/DuckLake database.
- Use `dbt debug` to inspect the profile and DuckDB connection.
- Use `dbt run` to execute the models and persist changes to the database.
- Use `dbt build` to execute and test all resources in the DAG.
- Use `dbt test` to run data tests.

## Conventions for building dbt models
- Avoid `SELECT *`.
- Use standard Jinja configs, e.g.: `{{ config(materialized='view') }}`.
- Describe the model inside `{{ config(description='...') }}`
- Use lowercase function names (e.g., `row_number()`).
- Use uppercase for SQL keywords (e.g., `PARTITION BY`).

## Conventions for Python models
- Ensure Python models `def model(dbt, session):` return a DataFrame from Polars, Pandas, or PyArrow.
- Use `dbt.config(materialized="table", ...)` strictly at the top of the function.
