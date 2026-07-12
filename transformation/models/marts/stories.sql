{{ config(
    materialized='view',
    description='Hacker News stories (posts) with author, score, and title.'
) }}

SELECT
    item_id AS story_id,
    author,
    created_at,
    title,
    url,
    score,
    comment_count
FROM {{ source('raw', 'items') }}
WHERE type = 'story'
