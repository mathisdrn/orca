# AGENTS.md - Orca

Orca is a data warehouse as-code implementation built around HackerNews data.

This project contains:
- `ingestion/`: dlt ingestion pipelines
- `transformation/`: dbt transformation pipelines
- `orchestration/`: Dagster orchestration code
- `storage/`: Database stored using DuckLake lakehouse format
- `analytics/`: Malloy semantics models and Streamlit dashboard
- `deployment/`: Deployment for Dagster read-only web UI
- `.github/workflows/`: Weekly data pipeline execution and Dagster UI serverless deployment in Google Cloud Run. Artifacts are force-pushed to GitHub but git-ignored for local-development.

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
- Warehouse artifacts are force-pushed to GitHub by the weekly warehouse execution but are git-ignored for local-development.
- Keep `README.md` and `AGENTS.md` up-to-date with latest development.

Best development practices:
- Test changes to the data pipeline Use `dg dev`
- Keep skills in-sync with deps ugprades