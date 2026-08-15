# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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