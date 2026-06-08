# AGENTS.md - transformation/

## Overview
dbt models and data warehouse layers:
- `models/a_raw/`: raw layer with ingestion models.
- `models/b_staging/`: staging layer with cleaning and normalization logic.
- `models/c_marts/`: marts layer.

## dbt CLI
- First, use `cd transformation/ && dbt ...`.
- Use `dbt debug` to inspect the profile and duckdb connection.
- Use `dbt run` to execute the pipeline and persist changes to the database.
- Use `dbt build` to execute and selectively test all resources in the DAG.
- Use `dbt test` to run tests on models.

## Conventions for building dbt models
- Avoid `SELECT *`.
- Use standard Jinja configs, eg: `{{ config(materialized='table') }}`.

## Conventions for Python models
- Ensure Python models `def model(dbt, session):` return a DataFrame from polars, pandas, or PyArrow.
- Use `dbt.config(materialized="table", ...)` strictly at the top of the function.

### SQL conventions
- Always describe the model inside `{{ config(description='...') }}` or in a corresponding `schema.yml` file.
