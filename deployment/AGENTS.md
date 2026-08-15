# AGENTS.md /deployment

This directory contains code related to deployment at `orca-datawarehouse.dev`. This includes:
- `orchestration/` displays Dagster UI in read-only mode. Runs on Cloud Run instance.
- `transformation/` displays dbt docs from `mathisdrn.github.io/orca/dbt-docs` (CNAME).
- `dashboard/` displays the embedded Streamlit dashboard (iframe).