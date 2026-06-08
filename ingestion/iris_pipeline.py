import dlt
import polars as pl

from ingestion.utils import PROJECT_ROOT, create_pipeline

GPKG_PATH = PROJECT_ROOT / "data" / "contours-iris-pe-2025.gpkg"


@dlt.resource(name="iris_borders", write_disposition="replace")
def load_iris_borders():
    """Load IRIS borders spatial data from the local GeoPackage file using the pipeline's SQL client.

    This resource queries the GeoPackage via the destination DuckDB client, which automatically
    has the spatial extension loaded.
    """
    pipeline = dlt.current.pipeline()
    with (
        pipeline.sql_client() as client,
        client.execute_query(
            """
            SELECT
                code_iris,
                nom_iris,
                type_iris,
                code_insee AS code_commune,
                ST_AsText(geometrie) AS geometrie
            FROM ST_Read(%s)
            WHERE ST_IsValid(geometrie)
            """,
            str(GPKG_PATH),
        ) as cursor,
    ):
        yield pl.from_arrow(cursor.arrow())


@dlt.source(name="iris_source")
def iris_source():
    """Dlt source containing the iris_borders resource."""
    return load_iris_borders


if __name__ == "__main__":
    # Create the pipeline using the centralized helper
    pipeline = create_pipeline(pipeline_name="iris_borders_ingestion")

    # Run the pipeline to extract, normalize and load the data
    load_info = pipeline.run(iris_source())
