# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-11-24

### Changed
- Flattened the Streamlit dashboard into `analytics/dashboard.py` with `analytics/.streamlit/config.toml` and minimal `analytics/requirements.txt` (`sqlglot<29`) for Streamlit Community Cloud.
- Configured DuckLake `ZSTD` (level 9) + Parquet v2 compression, replaced raw HTML `text` and duplicated `story_title`/`story_url` on comments with `text_length`, and pruned historical `storage/` blobs from Git history — shrinking `storage/` from 406 MB to 46 MB (~89% reduction).

## [0.5.0] - 2026-11-19

### Added
- Added `comments` semantic model in `analytics/model.py` (with `is_top_level`, `comment_length`, temporal seasonality dimensions, and `comment_share` / `top_level_rate` / `avg_comment_length` / `median_comment_length` / `top_level_comment_count` measures) joined to `stories` via `join_one(stories, on="story_id")`.
- Added `.streamlit/config.toml` configuring the minimalist editorial light theme (`#FFFFFF` canvas, `#F7F7F5` stone surface, `#18181B` ink, `#D95D1E` terracotta primary accent) and disabling usage stats collection.

### Changed
- Redesigned `analytics/dashboard/app.py` into a minimalist interactive dashboard powered by both `stories` and `comments` semantic models, featuring parameter-scoped `@st.cache_data` queries, a full-width dual-axis 7-day rolling stories/comments trend paired with weekday average story and point bar charts, full-width format and breakout story tables with clickable HackerNews links, nested reply depth analysis, and localized number formatting.
- Aligned `deployment/coldstart_loader.html` and `deployment/cloudflare_worker.js` to the minimalist editorial light theme (`#FFFFFF`, `#F7F7F5`, `#18181B`, `#D95D1E`).
- Enriched the `stories` semantic model in `analytics/model.py` with `story_type` (`ibis.cases`), URL `domain`, `is_discussed`/`is_traction` dimensions, temporal seasonality dimensions (`week`, `hour_of_day`, `day_of_week`), and `median_score` / `discussion_rate` / `traction_rate` / `active_days` / `avg_daily_stories` / `avg_daily_score` / `comments_per_point` / `story_share` measures with `.nullif(0)` denominator guards.
- Constrained `sqlglot<29` in `pyproject.toml` for `ibis-framework` 11.x compatibility with BSL `_.all()` measures on DuckDB and `sqlglot[rs]`.
- Upgraded `boring-semantic-layer` to `>=0.3.19` and simplified `analytics/model.py` so `link_story_count` and `show_ask_count` measures reference derived dimensions (`is_link`, `is_show_ask`) directly.
- Updated Duck-UI remote query URL in `README.md` to `duckui.com` with `DATA_PATH` and `OVERRIDE_DATA_PATH true` for DuckLake remote querying.
- Updated agent skills and cleaned up configurations, workflows, and documentation across ingestion, transformation, orchestration, analytics, and deployment.

### Fixed
- Guarded `_.story_id.isnull()` in `stories.story_type` so unmatched left-joined comments on pre-window stories or polls are no longer misclassified as `Self-Post` comments.
- Hardened domain extraction regex in `analytics/model.py` (`[^/?#:]+`) to strip query strings, fragments, and ports on root URLs.
- Fixed `None` KPI/narrative formatting crashes on null `comment_count`/`text` slices, added startup guards for empty/single-day warehouses, aligned 7-day rolling averages and weekday averages to calendar dates with complete 24-hour/7-weekday scaffolding, and added thread-safe locking with cache TTL for concurrent Streamlit sessions.

## [0.4.0] - 2026-10-25

### Added
- Implemented Python-native semantic model (`stories`) in `analytics/model.py` using `boring-semantic-layer` (`>=0.3.18`) and `ibis-framework[duckdb]` (`>=11.0.0`).
- Installed official Boring Semantic Layer agent skills (`bsl-model-builder` and `bsl-query-expert`).

### Changed
- Refactored Streamlit dashboard (`analytics/dashboard/app.py`) to query the BSL `stories` semantic model directly and use native Streamlit charts (`st.area_chart`, `st.bar_chart`).
- Simplified `deployment/Dockerfile.dagster` into a single-stage pure-Python 3.13 build and removed Node.js / `@malloydata/cli` steps from `.github/workflows/warehouse_execution.yml`.

### Removed
- Removed Malloy semantic layer files (`analytics/model.malloy`, `analytics/malloy-config.json`, `analytics/malloy_manifest.json`, `analytics/build_manifest.py`), `dagster-malloy`, `dagster-duckdb`, `altair`, and Malloy agent skills.

## [0.3.6] - 2026-10-21

### Changed
- Pinned `duckdb` and `duckdb-cli` to `<2` (`duckdb>=1.4.2,<2`, `duckdb-cli>=1.5.0,<2`) in core and deployment groups to ensure stability against day-zero DuckDB 2.0.0 regressions.
- Upgraded Polars to `v2.0.0`, PyArrow to `v26.0.0`, dlt to `v1.31.0`, Dagster to `v1.13.26`, Streamlit to `v1.66.1`, and Ruff to `v0.17.1`.
- Upgraded dbt core ecosystem (`dbt-core 1.12.6`).
- Simplified Ruff lint configuration in `pyproject.toml` by relying on Ruff's curated default rule set (413 rules) and keeping domain-specific data engineering extensions (`A`, `ICN`, `NPY`, `PD`, `SLF`, `T20`).

## [0.3.5] - 2026-09-15

### Added
- Added `/robots.txt` endpoint in Cloudflare Worker to prevent web crawlers from indexing serverless orchestration and docs backends.
- Added edge filtering for aggressive commercial scrapers and SEO bots (`AhrefsBot`, `SemrushBot`, etc.) with HTTP 403.
- Implemented edge caching (`Cache-Control: immutable`) for Next.js static assets in Cloudflare Worker to eliminate container wakeups and preserve GCP free egress quotas.

### Changed
- Updated Google Cloud billing spend cap / budget envelope from 1 € to 10 € to align with Cloud Run's gross catalog free tier envelope and prevent premature service suspensions.
- Documented gross billing vs net free tier considerations, anti-bot safeguards, and edge caching in `deployment/README.md` and `deployment/AGENTS.md`.

### Removed
- Removed `skip-worktree` recommendation from `README.md` to prevent merge and pull conflicts when pulling upstream warehouse updates.

## [0.3.4] - 2026-08-18

### Changed
- Configured explicit relative `pipelines_dir` for `dlt` inside `ingestion/.dlt/` (`ingestion/.dlt/pipelines/`) to ensure portable, isolated pipeline working directories and prevent polluting the user's home directory.
- Confirmed `.gitignore` rules for `dlt` pipeline cache and metadata.

## [0.3.3] - 2026-08-17

### Changed
- Structured core data warehouse dependencies in `pyproject.toml` grouped by architectural layer (Ingestion, Transformation, Orchestration, Storage, Analytics) and introduced isolated sub-groups for specialized targets (`deployment`, `dbt-docs`, `dev`).
- Replaced `dlt[duckdb,hub]` with `dlt[ducklake]`, dropped unused `plotly`, and made `pyarrow>=22.0.0` an explicit core dependency.
- Decoupled deployment and CI targets to install only required packages (`deployment` in Docker, `dbt-docs` in GitHub Pages build, and `--no-dev` in data warehouse execution).

### Fixed
- Fixed scheduled data warehouse execution failure in GitHub Actions caused by missing `pyarrow` during `dlt` data normalization/parquet writing and missing `duckdb-cli` during DuckLake cleanup.
- Updated `warehouse_execution.yml` workflow Node.js version from 20 to 22.

## [0.3.2] - 2026-08-15

### Added
- Documented fully qualified table naming best practices in `analytics/AGENTS.md`.

### Changed
- Upgraded `dagster-malloy` to `v0.2.7` with improved dialect resolution, clean database engine kind badges (`duckdb`), and enriched source/schema lineage metadata.
- Refactored Malloy model sources in `analytics/model.malloy` to use fully qualified table names (`marts.stories`, `marts.comments`).
- Simplified `orchestration/definitions.py` by removing `CustomMalloyTranslator` and relying on native multi-part asset lineage resolution.

## [0.3.1] - 2026-08-15

### Changed
- Standardized and uniformized all public domain routes on `orca-datawarehouse.dev` to strict singular paths (`/orchestration/`, `/transformation/`, `/dashboard/`).
- Updated Cloudflare Worker router to strictly match singular routes and updated dashboard route to `/dashboard/`.

### Fixed
- Corrected route references and typos in deployment documentation.

## [0.3.0] - 2026-08-13

### Added
- Native pre-compiled AST manifest (`malloy_manifest.json`) support in `dagster-malloy` eliminating Node.js runtime dependency in production container.
- Automatic AST manifest refresh on modification (`prepare_malloy_if_stale`) and warehouse-native CTAS materializations for Malloy assets.
- Image lifecycle policy and artifact retention rules in Cloud Run deployment workflow.
- Updated agent skills (`find-skills`, `skill-creator`, `motherduck-duckdb-sql`, `motherduck-load-data`, `motherduck-model-data`).

### Changed
- Upgraded core dependencies: `dagster` to `1.12.14`, `dagster-malloy` to `0.2.3`, `dlt` to `1.29.0`, `duckdb` to `1.4.2`, and `ruff` to `0.8.0`.
- Slimmed production Dagster container (`deployment/Dockerfile.dagster`) by separating deployment core dependencies from analytics tools.
- Increased live data polling rate and optimized container startup/cold-start loading scripts.

### Fixed
- Duplicate script tag causing timer freeze in cold-start loading screen.
- Resolved Malloy manifest extension configuration issues.

## [0.2.0] - 2026-08-09

### Added
- Integration of Malloy semantic assets into Dagster orchestration graph using custom asset translator.
- Cloud Run serverless deployment infrastructure for Dagster UI with OIDC authentication, ProxyGuard header protection, and fast cold-start loading page.
- Custom domain routing (`orca-datawarehouse.dev` and `www.orca-datawarehouse.dev`) via Cloudflare Worker proxy.
- Partition-based HackerNews data ingestion pipelines in `dlt`.

### Changed
- Refactored `dbt` project configurations and updated DuckLake catalog cleanup script (`storage/clean_ducklake.py`).
- Configured Streamlit dashboard iframe embedding on `/dashboards/`.

## [0.1.0] - 2026-07-12

### Added
- Initial release of Orca data warehouse as-code.
- HackerNews ingestion pipeline fetching stories, comments, and user profiles from Algolia REST API via `dlt`.
- Data transformation pipeline with `dbt` producing staged models and `marts` analytical views.
- DuckDB analytical database engine using `DuckLake` lakehouse catalog format and Parquet storage.
- Pipeline orchestration and observability using Dagster.
- Malloy semantic modeling layer and Streamlit analytics dashboard.
- GitHub Actions workflow for weekly automated warehouse execution.