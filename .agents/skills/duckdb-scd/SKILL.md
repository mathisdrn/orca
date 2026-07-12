---
name: duckdb-scd
description: Guides the implementation of Slowly Changing Dimensions (SCD Type 2) in DuckDB using the MERGE INTO statement (v1.4.0+). Use when building historical tracking tables, audit trails, or analytical dimensions in dbt or DuckDB SQL.
---

# DuckDB SCD Type 2 Implementation Guide

Use this guide to build Slowly Changing Dimensions (SCD Type 2) tables in DuckDB using the native `MERGE INTO` syntax introduced in DuckDB v1.4.0.

## Table Schema Conventions

An SCD Type 2 table tracks historical changes by keeping multiple versions of a business entity. To support this, design the target table with:
*   **Surrogate Key** (`record_id`): A unique primary key for each row version, typically managed using a sequence.
*   **Business Key** (`entity_id` / `duck_id`): The primary key from the source system.
*   **Dimension Attributes**: The columns whose history you want to track.
*   **Validity Fields**:
    *   `begin_date` (`DATE`): The date this version became active (inclusive).
    *   `end_date` (`DATE`): The date this version expired (inclusive). Set to `NULL` for the active version.
    *   `is_current` (`BOOLEAN`): Set to `true` for the active version, `false` for historical records.

### Creating Target Table & Sequence Example
```sql
CREATE SEQUENCE IF NOT EXISTS entity_record_seq START 1;

CREATE TABLE IF NOT EXISTS dim_entities (
    record_id   INTEGER PRIMARY KEY DEFAULT nextval('entity_record_seq'),
    entity_id   INTEGER NOT NULL,
    entity_name VARCHAR,
    location    VARCHAR,
    begin_date  DATE NOT NULL,
    end_date    DATE,
    is_current  BOOLEAN NOT NULL DEFAULT true
);
```

## The Two-Step SCD Type 2 Pattern

SCD Type 2 updates are done in two steps: a `MERGE` step to expire modified rows and insert brand-new ones, followed by a SELECT/INSERT step to insert the new versions of the expired rows.

### Step 1: Execute the MERGE Statement
This statement expires current versions of matching records that have changes, soft-deletes records that disappeared from the source, and inserts completely new records:

```sql
MERGE INTO dim_entities AS target
USING incoming_entities AS source
ON target.entity_id = source.entity_id AND target.is_current = true

-- 1. Expire existing matching records if attributes have changed
WHEN MATCHED AND (
    target.entity_name <> source.entity_name OR
    target.location    <> source.location
) THEN UPDATE SET
    end_date   = CURRENT_DATE - INTERVAL '1 day',
    is_current = false

-- 2. Soft-delete/expire records that disappeared from the source
WHEN NOT MATCHED BY SOURCE AND target.is_current = true THEN UPDATE SET
    end_date   = CURRENT_DATE - INTERVAL '1 day',
    is_current = false

-- 3. Insert brand new records
WHEN NOT MATCHED BY TARGET THEN INSERT (
    entity_id, entity_name, location, begin_date, end_date, is_current
) VALUES (
    source.entity_id, source.entity_name, source.location, CURRENT_DATE, NULL, true
);
```

### Step 2: Insert New Versions for Changed Records
Run an `INSERT` statement immediately after the `MERGE` to write the new current version of the records that were just expired in Step 1:

```sql
INSERT INTO dim_entities (
    entity_id, entity_name, location, begin_date, end_date, is_current
)
SELECT
    source.entity_id,
    source.entity_name,
    source.location,
    CURRENT_DATE AS begin_date,
    NULL AS end_date,
    true AS is_current
FROM incoming_entities AS source
INNER JOIN dim_entities AS target
ON source.entity_id = target.entity_id
WHERE target.is_current = false
  AND target.end_date = CURRENT_DATE - INTERVAL '1 day';
```

## Best Practices
*   **Transactions**: Wrap both the `MERGE` and `INSERT` steps in a single SQL transaction (`BEGIN TRANSACTION; ... COMMIT;`) to ensure data consistency.
*   **Current Row Filtering**: Keep `end_date` as `NULL` and `is_current = true` for active rows to allow fast indexing and simple analytical queries.
