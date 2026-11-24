# AGENTS.md - analytics/

This directory contains semantic models and reporting for the Orca data warehouse.

- Query warehouse data in dashboards and notebooks via the BSL semantic models in `analytics/model.py` (`READ_ONLY` over `orca.marts`) rather than raw SQL.
- On joined BSL semantic tables (`comments`), define measures against raw table columns rather than derived dimensions to avoid compile-time `AttributeError` scope errors.
- `analytics/requirements.txt` defines minimal dashboard-only dependencies so Streamlit Community Cloud skips installing the full repository `uv.lock` environment.
