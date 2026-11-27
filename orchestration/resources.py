import contextlib
from collections.abc import Generator

import dagster as dg
import duckdb


class DuckLakeResource(dg.ConfigurableResource):
    """DuckDB connection resource attached to the Orca DuckLake catalog."""

    catalog_path: str
    data_path: str

    @contextlib.contextmanager
    def connect(self) -> Generator[duckdb.DuckDBPyConnection]:
        """Open a DuckDB session attached to the configured DuckLake catalog."""
        escaped_catalog = self.catalog_path.replace("'", "''")
        escaped_data = self.data_path.replace("'", "''")
        with duckdb.connect() as con:
            con.execute("LOAD ducklake")
            con.execute(
                f"ATTACH 'ducklake:{escaped_catalog}' AS orca "
                f"(DATA_PATH '{escaped_data}', OVERRIDE_DATA_PATH true)"
            )
            con.execute("USE orca")
            yield con
