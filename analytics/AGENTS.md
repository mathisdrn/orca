# AGENTS.md - analytics/

This directory contains data analytics and semantic modeling code for the Orca data warehouse.

## Semantic Layer (BSL)
- The `stories` semantic model is defined in `analytics/model.py` using `boring-semantic-layer` on top of Ibis (`from ibis import _`).
- It queries `orca.marts.stories` in `READ_ONLY` mode from the local DuckLake catalog.
- Import the semantic model in dashboards or notebooks via `from analytics.model import stories`.
