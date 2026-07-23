-- This script clean the DuckLake before it's pushed to GitHub.
-- Run from project root: uv run duckdb < storage/clean_ducklake.sql

LOAD DUCKLAKE;
ATTACH 'ducklake:storage/orca.ducklake' AS orca (DATA_PATH 'storage/orca.ducklake.files/', OVERRIDE_DATA_PATH true);

-- Expire old snapshots and physically purge deleted/orphaned files
CALL ducklake_expire_snapshots('orca', older_than => now());
CALL ducklake_cleanup_old_files('orca', cleanup_all => true);
CALL ducklake_delete_orphaned_files('orca', cleanup_all => true);