import logging
import time
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import dlt
from dlt.common.schema.typing import TColumnSchema
from dlt.sources.helpers.rest_client import RESTClient

logger = logging.getLogger(__name__)


def fetch_items_by_window(
    client: RESTClient,
    start_ts: int,
    end_ts: int,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch Hacker News items for a given time window using the dlt RESTClient.

    Returns:
        A tuple of (hits, nb_hits) where hits is the list of records and
        nb_hits is the total matching hits reported by Algolia.
    """
    params = {
        "numericFilters": f"created_at_i>={start_ts},created_at_i<{end_ts}",
        "hitsPerPage": 1000,
    }

    # Fetch page 0
    response = client.get("search_by_date", params=params)
    data = response.json()

    nb_hits = data.get("nbHits", 0)
    hits = data.get("hits", [])
    nb_pages = data.get("nbPages", 1)

    # Fetch any extra pages if nb_pages > 1
    for page in range(1, nb_pages):
        page_params = {**params, "page": page}
        page_response = client.get("search_by_date", params=page_params)
        hits.extend(page_response.json().get("hits", []))

    return hits, nb_hits


DEFAULT_START_DATE = datetime(2026, 7, 1, tzinfo=UTC)

columns_schema: dict[str, TColumnSchema] = {
    "item_id": {"data_type": "bigint"},
    "author": {"data_type": "text"},
    "created_at": {"data_type": "timestamp"},
    "parent_id": {"data_type": "bigint"},
    "text": {"data_type": "text"},
    "story_id": {"data_type": "bigint"},
    "score": {"data_type": "bigint"},
    "comment_count": {"data_type": "bigint"},
    "title": {"data_type": "text"},
    "url": {"data_type": "text"},
    "type": {"data_type": "text"},
}


@dlt.resource(
    name="items",
    write_disposition="merge",
    primary_key="item_id",
    columns=columns_schema,
)
def hackernews_items(
    max_items: int | None = None,
    created_at_incremental: Any = dlt.sources.incremental(  # noqa: B008
        "created_at",
        initial_value=DEFAULT_START_DATE,
    ),
) -> Generator[dict[str, Any]]:
    """Hacker News items (stories, comments, polls, pollopts) fetched incrementally from the Algolia Search API.

    Dynamically adjusts window size to avoid exceeding Algolia's 1000 hit limit per query.
    """
    start_val = created_at_incremental.last_value
    if isinstance(start_val, (int, float)):
        start_ts = int(start_val)
    elif isinstance(start_val, str):
        start_ts = int(datetime.fromisoformat(start_val).timestamp())
    elif isinstance(start_val, datetime):
        start_ts = int(start_val.timestamp())
    else:
        start_ts = int(DEFAULT_START_DATE.timestamp())

    now_ts = int(time.time())

    start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(start_ts))
    now_date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now_ts))

    if start_ts >= now_ts - 60:
        logger.info(
            "Pipeline is up to date. Start time: %s (%d), Current: %s (%d)",
            start_date,
            start_ts,
            now_date,
            now_ts,
        )
        return

    logger.info(
        "Starting incremental ingestion from %s UTC (%d)...",
        start_date,
        start_ts,
    )

    # Initialize dlt RESTClient
    client = RESTClient(base_url="https://hn.algolia.com/api/v1")

    items_count = 0
    # Sliding window of 1 hour (3600 seconds)
    window_seconds = 3600

    while start_ts < now_ts:
        current_window = window_seconds

        while True:
            end_ts = min(start_ts + current_window, now_ts)
            if start_ts >= end_ts:
                break

            start_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(start_ts))
            end_date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(end_ts))

            logger.info(
                "Querying time window: %s to %s (%d to %d)...",
                start_date_str,
                end_date_str,
                start_ts,
                end_ts,
            )

            hits, nb_hits = fetch_items_by_window(client, start_ts, end_ts)

            # If the hits exceed 1000 and the window is greater than 1 second, bisect the window
            if nb_hits > 1000 and current_window > 1:
                new_window = max(1, current_window // 2)
                logger.warning(
                    "Window %s to %s (%d to %d) has %d hits (exceeds Algolia limit of 1000). Shrinking window size from %d to %d seconds.",
                    start_date_str,
                    end_date_str,
                    start_ts,
                    end_ts,
                    nb_hits,
                    current_window,
                    new_window,
                )
                current_window = new_window
                continue

            break

        logger.info("Retrieved %d items in this window.", len(hits))

        # Sort hits chronologically (ascending by created_at_i)
        hits.sort(key=lambda x: x.get("created_at_i", 0))

        for hit in hits:
            # Determine item type from tags
            raw_tags = hit.get("_tags", []) or []
            if "story" in raw_tags:
                item_type = "story"
            elif "comment" in raw_tags:
                item_type = "comment"
            elif "poll" in raw_tags:
                item_type = "poll"
            elif "pollopt" in raw_tags:
                item_type = "pollopt"
            else:
                item_type = "unknown"

            # Normalize and map fields
            item_id = int(hit["objectID"])
            created_at_i = hit.get("created_at_i")
            created_at = (
                datetime.fromtimestamp(created_at_i, UTC) if created_at_i else None
            )

            # Merge story_title and story_url into title and url
            title = hit.get("title") or hit.get("story_title")
            url = hit.get("url") or hit.get("story_url")

            yield {
                "item_id": item_id,
                "author": hit.get("author"),
                "created_at": created_at,
                "parent_id": hit.get("parent_id"),
                "text": hit.get("comment_text"),
                "story_id": hit.get("story_id"),
                "score": hit.get("points"),
                "comment_count": hit.get("num_comments"),
                "title": title,
                "url": url,
                "type": item_type,
            }

            items_count += 1

            if max_items is not None and items_count >= max_items:
                logger.info("Reached safety limit of %d items. Stopping.", max_items)
                return

        start_ts = end_ts

    logger.info(
        "Ingested %d items. Catch-up completed up to %s (%d).",
        items_count,
        now_date,
        now_ts,
    )


@dlt.source(name="hackernews_source")
def hackernews_source(max_items: int | None = None) -> list[Any]:
    """The dlt source for Hacker News items."""
    return [hackernews_items(max_items=max_items)]
