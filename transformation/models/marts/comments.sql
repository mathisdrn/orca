{{ config(
    materialized='view',
    description='Hacker News comments with character length and references to parent story or comment.'
) }}

SELECT
    item_id AS comment_id,
    author,
    created_at,
    parent_id,
    text_length,
    story_id
FROM {{ source('raw', 'items') }}
WHERE type = 'comment'
