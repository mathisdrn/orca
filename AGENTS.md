# AGENTS.md - Orca

Orca is a data warehouse as-code implementation built on modern and free tools. It provides a comprehensive framework for data ingestion, transformation, orchestration, storage, compute, semantic layers, analytics and deployments.

Orca is designed to be easy to adopt, extend and reuse. Orca lightweight data model is built on HackerNews data from the Algolia REST API. 

It features built-in documentation and workflows for humans and AI agents.

This project contains:
- `ingestion/`: dlt ingestion pipelines
- `transformation/`: dbt transformation pipelines
- `orchestration/`: Dagster orchestration code
- `storage/`: Database stored using DuckLake lakehouse format
- `analytics/`: Malloy semantics models and Streamlit dashboard
- `deployment/`: Deployment for Dagster read-only web UI
- `.github/workflows/`: Weekly warehouse execution and Dagster UI serverless deployment in Google Cloud Run.

This project uses:
- `duckdb` as the query engine and DuckLake catalog
- `uv` for Python environment (use `uv run`)
- `ruff` for linting and formatting
- `npx skills` for managing agent skills
- `gcloud` for Google Cloud platform
- `npx wrangler` for Cloudflare environment
- `gh` CLI to interact with GitHub
- `malloy-cli` to interact with Malloy semantics models
- `dbt` CLI for dbt transformations
- `dg` for Dagster orchestrations

Additional information:
- Warehouse artifacts (database, dbt `manifest.json`, Dagster logs) are git-ignored for local-development but force-pushed during GitHub Actions weekly warehouse execution.

Development practices:
- Keep `README.md` and `AGENTS.md` up-to-date with developments.
- Documents changes in `CHANGELOG.md` and update versions in `pyproject.toml`.
- Keep skills in-sync with deps upgrades.