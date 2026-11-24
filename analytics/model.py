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

stories = (
    to_semantic_table(
        ibis_con.table("stories", database=("orca", "marts")), name="stories"
    )
    .with_dimensions(
        story_id=_.story_id,
        author=_.author,
        created_at=_.created_at,
        day=_.created_at.truncate("D"),
        week=_.created_at.truncate("W"),
        hour_of_day=_.created_at.hour(),
        day_of_week=_.created_at.day_of_week.full_name(),
        title=_.title,
        url=_.url,
        domain=_.url.re_extract(r"https?://(?:www\.)?([^/?#:]+)", 1).nullif(""),
        is_link=_.url.notnull(),
        is_discussed=_.comment_count > 0,
        is_traction=_.score >= 10,
        is_show_ask=_.title.startswith("Show HN:") | _.title.startswith("Ask HN:"),
        story_type=ibis.cases(
            (_.story_id.isnull(), None),
            (_.title.startswith("Show HN:"), "Show HN"),
            (_.title.startswith("Ask HN:"), "Ask HN"),
            (_.title.startswith("Tell HN:"), "Tell HN"),
            (_.title.startswith("Launch HN:"), "Launch HN"),
            (_.url.isnull(), "Self-Post"),
            else_="Link",
        ),
    )
    .with_measures(
        story_count=_.count(),
        unique_author_count=_.author.nunique(),
        total_score=_.score.sum(),
        avg_score=_.score.mean(),
        median_score=_.score.median(),
        max_score=_.score.max(),
        total_comments=_.comment_count.sum(),
        avg_comments=_.comment_count.mean(),
        comments_per_point=_.total_comments / _.total_score.nullif(0),
        story_share=_.story_count / _.all(_.story_count),
        link_story_count=_.is_link.sum(),
        discussed_story_count=_.is_discussed.sum(),
        discussion_rate=_.discussed_story_count / _.story_count.nullif(0),
        traction_story_count=_.is_traction.sum(),
        traction_rate=_.traction_story_count / _.story_count.nullif(0),
        show_ask_count=_.is_show_ask.sum(),
        active_days=_.day.nunique(),
        avg_daily_stories=_.story_count / _.active_days.nullif(0),
        avg_daily_score=_.total_score / _.active_days.nullif(0),
        min_created_at=_.created_at.min(),
        max_created_at=_.created_at.max(),
    )
)

comments = (
    to_semantic_table(
        ibis_con.table("comments", database=("orca", "marts")), name="comments"
    )
    .with_dimensions(
        comment_id=_.comment_id,
        author=_.author,
        created_at=_.created_at,
        day=_.created_at.truncate("D"),
        week=_.created_at.truncate("W"),
        hour_of_day=_.created_at.hour(),
        day_of_week=_.created_at.day_of_week.full_name(),
        parent_id=_.parent_id,
        story_id=_.story_id,
        is_top_level=_.parent_id == _.story_id,
        comment_length=_.text_length,
    )
    .with_measures(
        comment_count=_.count(),
        unique_author_count=_.author.nunique(),
        top_level_comment_count=(_.parent_id == _.story_id).sum(),
        top_level_rate=_.top_level_comment_count / _.comment_count.nullif(0),
        avg_comment_length=_.text_length.mean(),
        median_comment_length=_.text_length.median(),
        comment_share=_.comment_count / _.all(_.comment_count),
        min_created_at=_.created_at.min(),
        max_created_at=_.created_at.max(),
    )
    .join_one(stories, on="story_id")
)
