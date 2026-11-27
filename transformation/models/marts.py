import ibis
from ibis import _

from transformation.engine.compiler import model
from transformation.models.sources import raw_items


@model(
    db_schema="marts",
    materialized="view",
    primary_key="story_id",
    columns={
        "story_id": "Unique identifier of the story.",
        "author": "Username of the author.",
        "created_at": "Timestamp of when the story was created.",
        "title": "Title of the story.",
        "url": "URL of the story.",
        "score": "Score of the story (points).",
        "comment_count": "Number of comments on the story.",
    },
)
def stories() -> ibis.Table:
    """Hacker News stories (posts) containing author, score (points), title, URL, and comment counts."""
    return raw_items.filter(_.type == "story").select(
        story_id=_.item_id,
        author=_.author,
        created_at=_.created_at,
        title=_.title,
        url=_.url,
        score=_.score,
        comment_count=_.comment_count,
    )


@model(
    db_schema="marts",
    materialized="view",
    primary_key="comment_id",
    columns={
        "comment_id": "Unique identifier of the comment.",
        "author": "Username of the author.",
        "created_at": "Timestamp of when the comment was created.",
        "parent_id": "ID of the parent story or parent comment.",
        "text_length": "Character length of the comment text.",
        "story_id": "ID of the root parent story.",
    },
)
def comments() -> ibis.Table:
    """Hacker News comments containing character length and references to parent items and root stories."""
    return raw_items.filter(_.type == "comment").select(
        comment_id=_.item_id,
        author=_.author,
        created_at=_.created_at,
        parent_id=_.parent_id,
        text_length=_.text_length,
        story_id=_.story_id,
    )
