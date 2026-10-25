from pathlib import Path

import duckdb
import ibis
from boring_semantic_layer import to_semantic_table
from ibis import _

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "storage" / "orca.ducklake"
FILES_DIR = PROJECT_ROOT / "storage" / "orca.ducklake.files"

con = duckdb.connect()
con.execute(
    f"ATTACH 'ducklake:{DB_PATH}' AS orca (DATA_PATH '{FILES_DIR.as_posix()}/', OVERRIDE_DATA_PATH true, READ_ONLY)"
)
ibis_con = ibis.duckdb.from_connection(con)

_is_link = _.url.notnull()
_is_show_ask = _.title.startswith("Show HN:") | _.title.startswith("Ask HN:")

stories = (
    to_semantic_table(
        ibis_con.table("stories", database=("orca", "marts")), name="stories"
    )
    .with_dimensions(
        story_id=_.story_id,
        author=_.author,
        created_at=_.created_at,
        day=_.created_at.truncate("D"),
        title=_.title,
        url=_.url,
        is_link=_is_link,
        is_show_ask=_is_show_ask,
    )
    .with_measures(
        story_count=_.count(),
        unique_author_count=_.author.nunique(),
        total_score=_.score.sum(),
        avg_score=_.score.mean(),
        max_score=_.score.max(),
        total_comments=_.comment_count.sum(),
        avg_comments=_.comment_count.mean(),
        link_story_count=_is_link.sum(),
        show_ask_count=_is_show_ask.sum(),
        min_created_at=_.created_at.min(),
        max_created_at=_.created_at.max(),
    )
)
