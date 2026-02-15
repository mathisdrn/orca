# AGENTS.md — modern-data-platform

Global guidance for agentic coding agents working in this repo.
Sub-folder `AGENTS.md` files override these rules for their specific context.

## Project overview

**modern-data-platform** composes free, open-source Modern Data Stack tools into
a self-contained, versioned, production-ready, and LLM-friendly data warehouse.

The intended workflow is daily or hourly batch refresh (not real-time streaming).

## Tech stack

| Layer | Tool | Status |
|---|---|---|
| Environment | [uv](https://docs.astral.sh/uv/) | Active |
| Database | [DuckDB](https://duckdb.org/) | Active |
| Transformation | [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/) | Active |
| Orchestration | [Dagster](https://dagster.io/) | Planned |
| Ingestion | [dlt](https://dlthub.com/) | Planned |
| Storage layer | [DuckLake](https://ducklake.select/) | Planned |
| Reporting | [Evidence](https://evidence.dev/) | Planned |

- Python `>=3.13` (`pyproject.toml`), managed with `uv`.

## Repository structure

```
root/
├── AGENTS.md              # This file — global rules and conventions
├── .agents/               # Agent config, SKILL and Persona definitions
│   ├── data-engineer.md
│   └── analyst.md
├── analytics/             # Analytics / ML module (future)
│   └── __init__.py
├── ingestion/             # dlt pipelines (future)
├── reporting/             # Dashboards (future)
├── transformation/        # SQLMesh pipeline (DuckDB backend)
│   ├── config.yaml
│   ├── models/
│   │   ├── a_raw/         # Raw layer: ingestion models
│   │   ├── b_staging/     # Staging layer: cleaning & normalization
│   │   └── c_marts/       # Marts layer: business-ready tables
│   ├── seeds/             # CSV seed files for reference data
│   ├── audits/
│   ├── macros/
│   └── tests/
├── data/                  # Local DuckDB database (git-ignored)
├── pyproject.toml         # Python deps, ruff config, build
└── uv.lock
```

## Setup

```bash
uv sync  # Create venv and install dependencies
```

## Common commands

### Python (uv)

```bash
uv sync                         # Install/sync dependencies
uv venv --clear && uv sync      # Recreate venv from scratch
```

### SQLMesh pipeline (`transformation/`)

```bash
cd transformation && sqlmesh plan --auto-apply   # Plan + auto-apply changes
cd transformation && sqlmesh run                 # Run pipeline
cd transformation && sqlmesh plan -m <model_name> --auto-apply  # Single model
```

Model naming convention: `a_raw.*`, `b_staging.*`, `c_marts.*`.

### DuckDB

```bash
duckdb -ui data/db.duckdb       # Open DuckDB UI
```

## Lint / format

### Python (ruff)

```bash
uv run ruff format .            # Format
uv run ruff check --fix .       # Lint + auto-fix
```

### SQL (SQLMesh)

```bash
cd transformation && sqlmesh lint
```

Rules configured in `transformation/config.yaml`.

## Testing

```bash
cd transformation && sqlmesh lint             # SQLMesh lint
uv run ruff check . && cd transformation && sqlmesh lint  # ruff + sqlmesh lint
```

No Python unit test suite yet (`transformation/tests/.gitkeep`).

## Code style

### General

- Prefer small, reviewable PRs: isolate behavior changes.
- Keep side effects explicit: separate data fetching, transformation, and persistence.
- Do not write to `data/` at import time; do it in functions/entrypoints.

### Python imports

- Prefer explicit imports over `import *`.
- Use `collections.abc` for typing iterables.
- Use explicit `from typing import X` imports. Do not use `import typing as t`.

### Types and annotations

- Use type hints for public functions and non-trivial helpers.
- Prefer `collections.abc` types: `Iterator`, `Iterable`, `Sequence`, etc.
- Use `typing.Any` only at integration boundaries.

### Naming conventions

- SQLMesh models: `a_raw.*`, `b_staging.*`, `c_marts.*`.
- Column names: `snake_case`.

### Error handling and logging

- Avoid bare `except:`; catch `Exception` at boundaries only.
- Prefer structured logging (`logging` module) over `print` for libraries.
- Include enough context for debugging (what operation failed, exception message).
- Re-raise if failure should abort the run.

### Polars usage

- Prefer Polars for DataFrame operations in Python models.
- Keep column naming consistent: `snake_case`.

### SQL style (DuckDB / SQLMesh)

- Keep `SELECT` lists explicit; avoid `SELECT *` in staging and marts.
- Use consistent casing for SQL keywords (match surrounding code).
- Prefer CTEs for multi-step transforms.

### Python SQLMesh models

Conventions for Python-based SQLMesh models (`transformation/models/`):

- **Column types in `@model` decorator**: use lowercase (`"date"`, `"text"`, `"float"`).
- **Reference data (seeds)**: static reference data lives in CSV seed files under
  `transformation/seeds/`. Python models read from seed tables at runtime via
  `context.resolve_table()` + `context.fetchdf()`. Do not hardcode reference data
  inline in model files.
- **Returning empty DataFrames**: Python models may not return an empty DataFrame.
  If your model could possibly return an empty DataFrame, conditionally yield it
  or return an empty generator instead:

  ```python
  if df.is_empty():
      yield from ()
  else:
      yield df
  ```

- **Error handling**: catch `Exception` at the top level, log with
  `logger.exception(...)` for full traceback context, then re-raise so the
  pipeline fails visibly on persistent errors.

## Repo-specific notes

- Local DB path: `data/db.duckdb` (see `transformation/config.yaml`).
- `data/` and `logs/` are local artifacts, git-ignored.

Data Analyst Best Practices:
- Query from `c_marts.*` tables whenever possible; avoid querying raw or staging
- Document assumptions and methodology in reports.
- Prefer explicit `SELECT` lists over `SELECT *`.
