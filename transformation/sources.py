from ingestion.hackernews import hackernews_source
from transformation.engine import register_dlt_source

raw = register_dlt_source(hackernews_source(), db_schema="raw")
raw_items = raw["items"]
