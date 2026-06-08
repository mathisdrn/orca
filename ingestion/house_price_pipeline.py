import dlt
import polars as pl

from ingestion.utils import PROJECT_ROOT, create_pipeline

PARQUET_PATH = PROJECT_ROOT / "data" / "house-price.parquet"


@dlt.resource(name="house_prices", write_disposition="replace")
def load_house_prices():
    """Load house price data from the local Parquet file using Polars.

    This resource yields a Polars DataFrame directly, taking advantage of dlt's
    native Arrow/Polars/Pandas support for fast columnar data loading.
    """
    yield pl.read_parquet(PARQUET_PATH)


@dlt.source(name="house_price_source")
def house_price_source():
    """Dlt source containing the house_prices resource."""
    return load_house_prices


if __name__ == "__main__":
    # Create the pipeline using the centralized helper
    pipeline = create_pipeline(pipeline_name="house_price_ingestion")

    # Run the pipeline to extract, normalize and load the data
    load_info = pipeline.run(house_price_source())
