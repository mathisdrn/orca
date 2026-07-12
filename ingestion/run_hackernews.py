import logging

from ingestion.hackernews import hackernews_source
from ingestion.utils import create_pipeline

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = create_pipeline(pipeline_name="hackernews_ingestion")

    # Run for a small window of 10 items for direct execution test
    logger.info("Starting local pipeline execution...")
    load_info = pipeline.run(hackernews_source(max_items=10))
    logger.info("Load finished:\n%s", load_info)
