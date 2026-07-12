{{ config(
    materialized='view',
    description='Hacker News comments, containing comment text and reference to parent story or comment.'
) }}

SELECT
    item_id AS comment_id,
    author,
    created_at,
    parent_id,
    text,
    story_id,
    title AS story_title,
    url AS story_url
FROM {{ source('raw', 'items') }}
WHERE type = 'comment'