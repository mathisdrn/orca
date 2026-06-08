import dlt
import polars as pl

from ingestion.utils import PROJECT_ROOT, create_pipeline

PRODUCTS_PATH = PROJECT_ROOT / "data" / "products.csv"


@dlt.resource(name="products", write_disposition="replace")
def load_products():
    """Load mock product data from the local CSV file using Polars.

    This resource yields a Polars DataFrame directly, taking advantage of dlt's
    native Arrow/Polars/Pandas support for fast columnar data loading.
    """
    yield pl.read_csv(PRODUCTS_PATH)


@dlt.source(name="products_source")
def products_source():
    """Dlt source containing the products resource."""
    return load_products


if __name__ == "__main__":
    # Create the pipeline using the centralized helper
    pipeline = create_pipeline(pipeline_name="products_ingestion")

    # Run the pipeline to extract, normalize and load the data
    load_info = pipeline.run(products_source())
