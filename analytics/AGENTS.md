# AGENTS.md - analytics/

This directory contains data analytics and semantic modeling code for the Orca data warehouse.

## Semantic Layer (BSL)
- The `stories` and `comments` semantic models are defined in `analytics/model.py` using `boring-semantic-layer` on top of Ibis (`from ibis import _`).
- `comments` joins `stories` via `.join_one(stories, on="story_id")`, so queries on `comments` use prefixed field names (e.g., `comments.comment_count`, `stories.story_type`).
- `stories.story_type` guards `_.story_id.isnull()` so unmatched left-joined comments are not bucketed as `Self-Post`, and `comments` measures reference raw table columns rather than derived dimensions to avoid BSL join scope errors.
- Both models query the `orca.marts` layer in `READ_ONLY` mode from the local DuckLake catalog.
- Import the semantic models in dashboards or notebooks via `from analytics.model import stories, comments`.
- The Streamlit dashboard minimalist editorial light theme (`base = "light"`, `primaryColor = "#D95D1E"`, `backgroundColor = "#FFFFFF"`, `secondaryBackgroundColor = "#F7F7F5"`, `textColor = "#18181B"`) is configured in `.streamlit/config.toml`.
