-- Script to create or configure Orca DuckLake with recommended settings.
-- Run from project root: uv run duckdb < storage/configure_ducklake.sql
--
-- DATA_PATH notes:
--   - DuckLake resolves all relative paths against the CWD, NOT the catalog file location.
--   - DATA_PATH must be specified on first creation; it is stored in the catalog.
--   - On re-attach, the stored path is loaded automatically — DATA_PATH is ignored
--     unless OVERRIDE_DATA_PATH = true (session-only override, does not persist).
--   - Always run this script from the project root so that relative paths resolve correctly.

LOAD DUCKLAKE;

-- Create or re-attach DuckLake with DATA_PATH relative to project root.
-- OVERRIDE_DATA_PATH true:
--   • First run: stores 'orca.ducklake.files/' in the catalog (relative to project root).
--   • Re-run on ducklake with absolute path baked in: overrides for current session only.
ATTACH 'ducklake:storage/orca.ducklake' AS orca (DATA_PATH 'orca.ducklake.files/', OVERRIDE_DATA_PATH true);

-- Configure DuckLake options (persisted to catalog).
CALL orca.set_option('target_file_size', '90MB');
CALL orca.set_option('parquet_version', '2');
CALL orca.set_option('auto_compact', false);

-- Inspect options and settings.
FROM orca.options();
FROM orca.settings();