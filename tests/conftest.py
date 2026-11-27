from collections.abc import Callable
from pathlib import Path

import dlt
import duckdb
import ibis
import pytest

from transformation.engine.compiler import register_dlt_source, reset_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset the transformation model registry and validator before/after each test."""
    reset_registry()
    yield
    reset_registry()


@pytest.fixture()
def ducklake_con(tmp_path: Path):
    """Create an isolated DuckLake catalog with a seeded raw.items source table."""
    catalog = tmp_path / "test.ducklake"
    files_dir = tmp_path / "test.ducklake.files"
    con = duckdb.connect()
    con.execute("LOAD ducklake")
    con.execute(
        f"ATTACH 'ducklake:{catalog.as_posix()}' AS orca "
        f"(DATA_PATH '{files_dir.as_posix()}/', OVERRIDE_DATA_PATH true); USE orca;"
    )
    con.execute("CREATE SCHEMA raw")
    con.execute(
        """
        CREATE TABLE raw.items (
            item_id BIGINT,
            author VARCHAR,
            score BIGINT,
            title VARCHAR,
            updated_at TIMESTAMPTZ,
            kind VARCHAR
        )
        """
    )
    yield con, catalog, files_dir
    con.close()


def _build_raw_items() -> ibis.Table:
    """Register a typed dlt source matching the test DuckLake raw.items table."""

    @dlt.resource(
        name="items",
        columns={
            "item_id": {"data_type": "bigint", "nullable": False, "primary_key": True},
            "author": {"data_type": "text"},
            "score": {"data_type": "bigint"},
            "title": {"data_type": "text"},
            "updated_at": {"data_type": "timestamp"},
            "kind": {"data_type": "text"},
        },
    )
    def items_res():
        yield from ()

    @dlt.source(name="test_hn")
    def test_src():
        return [items_res()]

    return register_dlt_source(test_src(), db_schema="raw")["items"]


@pytest.fixture()
def make_raw_items() -> Callable[[], ibis.Table]:
    """Provide a factory that registers a fresh typed dlt source for raw.items."""
    return _build_raw_items
