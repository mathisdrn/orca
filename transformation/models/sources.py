from ingestion.hackernews import hackernews_source
from transformation.engine.compiler import register_dlt_source

_raw_tables = register_dlt_source(hackernews_source(), db_schema="raw")
raw_items = _raw_tables["items"]
