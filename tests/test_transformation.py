from datetime import UTC, datetime, timedelta

import ibis
import pytest
from ibis import _

from transformation.engine.compiler import model, reset_registry
from transformation.engine.executor import materialize_model


def test_view_and_table_transitions_and_code_version(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 10, 'Hello', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')"
    )
    raw = make_raw_items()

    @model(db_schema="marts", materialized="view", primary_key="story_id")
    def items_view() -> ibis.Table:
        """Story view."""
        return raw.filter(_.kind == "story").select(
            story_id=_.item_id, author=_.author, score=_.score
        )

    v_stats = materialize_model(con, items_view)
    assert v_stats.row_count == 1
    assert v_stats.rows_affected is None
    assert not v_stats.rolled_back
    assert len(items_view.code_version) == 12

    reset_registry()
    raw2 = make_raw_items()

    @model(
        db_schema="marts",
        materialized="table",
        primary_key="story_id",
        columns={"story_id": "PK", "score": "Points"},
    )
    def items_view() -> ibis.Table:
        """Story table."""
        return raw2.filter(_.kind == "story").select(
            story_id=_.item_id, author=_.author, score=_.score
        )

    t_stats = materialize_model(con, items_view)
    assert t_stats.row_count == 1
    assert t_stats.rows_affected == 1
    assert (
        con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'items_view'"
        ).fetchall()[0][0]
        == 1
    )
    col_comments = dict(
        con.execute(
            "SELECT column_name, comment FROM duckdb_columns() WHERE table_name = 'items_view'"
        ).fetchall()
    )
    assert col_comments["score"] == "Points"


def test_code_version_changes_with_lookback(make_raw_items) -> None:
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        lookback=timedelta(hours=12),
        primary_key="story_id",
    )
    def m_lookback() -> ibis.Table:
        return raw.select(story_id=_.item_id, updated_at=_.updated_at)

    v1 = m_lookback.code_version
    reset_registry()
    raw2 = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        lookback=timedelta(hours=24),
        primary_key="story_id",
    )
    def m_lookback() -> ibis.Table:
        return raw2.select(story_id=_.item_id, updated_at=_.updated_at)

    assert m_lookback.code_version != v1


def test_incremental_merge_watermark_lookback_and_schema_evolution(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'S1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story'),
            (2, 'bob', 20, 'S2', TIMESTAMPTZ '2026-07-02 00:00:00+00', 'story')
        """
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        lookback=timedelta(hours=12),
        primary_key="story_id",
    )
    def inc_stories() -> ibis.Table:
        """Incremental stories."""
        return raw.filter(_.kind == "story").select(
            story_id=_.item_id,
            score=_.score,
            updated_at=_.updated_at,
        )

    s1 = materialize_model(con, inc_stories)
    assert s1.row_count == 2
    assert s1.rows_affected == 2

    # Test empty 0-row target table (max_watermark is None) runs unfiltered on next load
    con.execute("DELETE FROM marts.inc_stories")
    s_empty = materialize_model(con, inc_stories)
    assert s_empty.row_count == 2

    # Update row 2 inside lookback window, insert row 3, and evolve schema with mid-projection column
    con.execute(
        """
        UPDATE raw.items SET score = 99, updated_at = TIMESTAMPTZ '2026-07-01 18:00:00+00' WHERE item_id = 2;
        INSERT INTO raw.items VALUES (3, 'carol', 30, 'S3', TIMESTAMPTZ '2026-07-03 00:00:00+00', 'story');
        """
    )
    reset_registry()
    raw2 = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        lookback=timedelta(hours=12),
        primary_key="story_id",
    )
    def inc_stories() -> ibis.Table:
        """Incremental stories with evolved mid-projection column."""
        return raw2.filter(_.kind == "story").select(
            story_id=_.item_id,
            author=_.author,
            score=_.score,
            updated_at=_.updated_at,
        )

    s2 = materialize_model(con, inc_stories)
    assert s2.row_count == 3
    assert s2.rows_affected == 2
    rows = con.execute(
        "SELECT story_id, author, score FROM marts.inc_stories ORDER BY story_id"
    ).fetchall()
    assert rows == [(1, None, 10), (2, "bob", 99), (3, "carol", 30)]

    # Verify full_refresh rebuilds cleanly with column order & historical author backfilled
    s3 = materialize_model(con, inc_stories, full_refresh=True)
    assert s3.row_count == 3
    rows_full = con.execute(
        "SELECT story_id, author, score FROM marts.inc_stories ORDER BY story_id"
    ).fetchall()
    assert rows_full == [(1, "alice", 10), (2, "bob", 99), (3, "carol", 30)]


def test_incremental_schema_evolution_adding_incremental_key(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 10, 'S1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')"
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        primary_key="story_id",
    )
    def evolved_wm() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score)

    materialize_model(con, evolved_wm)

    reset_registry()
    raw2 = make_raw_items()
    con.execute(
        "INSERT INTO raw.items VALUES (2, 'bob', 20, 'S2', TIMESTAMPTZ '2026-07-02 00:00:00+00', 'story')"
    )

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        primary_key="story_id",
    )
    def evolved_wm() -> ibis.Table:
        return raw2.select(story_id=_.item_id, score=_.score, updated_at=_.updated_at)

    s2 = materialize_model(con, evolved_wm)
    assert s2.row_count == 2
    assert s2.rows_affected == 2


def test_incremental_merge_rejects_duplicate_incoming_pk(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 10, 'S1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')"
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        primary_key="story_id",
    )
    def dup_inc() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score)

    materialize_model(con, dup_inc)
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 20, 'S1-dup', TIMESTAMPTZ '2026-07-02 00:00:00+00', 'story')"
    )
    with pytest.raises(ValueError, match="duplicate primary_key rows"):
        materialize_model(con, dup_inc)


def test_incremental_delete_insert_window_and_watermark(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'D1', TIMESTAMPTZ '2026-07-01 10:00:00+00', 'story'),
            (2, 'bob', 20, 'D2', TIMESTAMPTZ '2026-07-02 10:00:00+00', 'story')
        """
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="delete_insert",
        incremental_key="updated_at",
        lookback=timedelta(hours=12),
    )
    def events_di() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score, updated_at=_.updated_at)

    s1 = materialize_model(con, events_di)
    assert s1.row_count == 2

    # Bounded window overwrite on July 2 only: rows_affected reports inserted rows (1)
    con.execute(
        "UPDATE raw.items SET score = 200 WHERE item_id = 2;"
        "INSERT INTO raw.items VALUES (3, 'carol', 30, 'D3', TIMESTAMPTZ '2026-07-03 10:00:00+00', 'story');"
    )
    s2 = materialize_model(
        con,
        events_di,
        window=(
            datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            datetime(2026, 7, 3, 0, 0, tzinfo=UTC),
        ),
    )
    assert s2.rows_affected == 1
    assert s2.row_count == 2
    assert (
        con.execute("SELECT score FROM marts.events_di WHERE story_id = 2").fetchall()[
            0
        ][0]
        == 200
    )

    # Open-ended watermark + lookback picks up July 3 without losing July 1-2
    s3 = materialize_model(con, events_di)
    assert s3.row_count == 3


def test_incremental_date_window_coercion(ducklake_con, make_raw_items) -> None:
    con = ducklake_con[0]
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'D1', TIMESTAMPTZ '2026-07-01 10:00:00+00', 'story'),
            (2, 'bob', 20, 'D2', TIMESTAMPTZ '2026-07-02 10:00:00+00', 'story')
        """
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="delete_insert",
        incremental_key="updated_date",
    )
    def daily_events() -> ibis.Table:
        return raw.select(
            story_id=_.item_id,
            score=_.score,
            updated_date=_.updated_at.date(),
        )

    materialize_model(con, daily_events)
    con.execute("UPDATE raw.items SET score = 99 WHERE item_id = 2")
    s2 = materialize_model(
        con,
        daily_events,
        window=(
            datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            datetime(2026, 7, 3, 0, 0, tzinfo=UTC),
        ),
    )
    assert s2.rows_affected == 1
    assert (
        con.execute(
            "SELECT score FROM marts.daily_events WHERE story_id = 2"
        ).fetchall()[0][0]
        == 99
    )


def test_scd2_changes_snapshot_chaining_and_transition_guard(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'V1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story'),
            (2, 'bob', 20, 'V1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')
        """
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="scd2",
        scd2_mode="snapshot",
        primary_key="story_id",
        valid_from_col="updated_at",
    )
    def dim_stories() -> ibis.Table:
        """SCD2 story dimension."""
        return raw.select(
            story_id=_.item_id,
            score=_.score,
            updated_at=_.updated_at,
        )

    # Downstream model referencing SCD2 metadata column `is_current` must pass compile-time DDL validation
    @model(db_schema="marts", materialized="view", primary_key="story_id")
    def dim_stories_current() -> ibis.Table:
        return dim_stories.table.filter(_.is_current).select(
            _.story_id, _.score, _.valid_from
        )

    assert "is_current" in dim_stories.ibis_schema.names
    assert "updated_at" not in dim_stories.tracked_columns

    s1 = materialize_model(con, dim_stories)
    assert s1.row_count == 2
    assert s1.duplicate_counts[("story_id",)] == 0

    # Idempotent rerun at same timestamp + untouched tracked columns: no duplicate active rows
    s_rerun = materialize_model(con, dim_stories)
    assert s_rerun.row_count == 2
    assert s_rerun.rows_affected == 0

    # Touch only updated_at on story 2 (should NOT create new version), change score on story 1, delete story 2
    con.execute(
        """
        UPDATE raw.items SET score = 55, updated_at = TIMESTAMPTZ '2026-07-02 00:00:00+00' WHERE item_id = 1;
        DELETE FROM raw.items WHERE item_id = 2;
        INSERT INTO raw.items VALUES (3, 'carol', 30, 'V1', TIMESTAMPTZ '2026-07-02 00:00:00+00', 'story');
        """
    )
    s2 = materialize_model(con, dim_stories)
    assert s2.duplicate_counts[("story_id",)] == 0

    versions_1 = con.execute(
        "SELECT score, valid_from, valid_to, is_current FROM marts.dim_stories WHERE story_id = 1 ORDER BY valid_from"
    ).fetchall()
    assert len(versions_1) == 2
    assert versions_1[0][0] == 10 and versions_1[0][3] is False
    assert versions_1[1][0] == 55 and versions_1[1][3] is True
    # Timeline continuity: old.valid_to == new.valid_from (no inversion)
    assert versions_1[0][2] == versions_1[1][1]

    story2_current = con.execute(
        "SELECT is_current FROM marts.dim_stories WHERE story_id = 2"
    ).fetchall()[0][0]
    assert story2_current is False

    cur_view = materialize_model(con, dim_stories_current)
    assert cur_view.row_count == 2

    # Transitioning scd2 -> incremental without full_refresh=True must raise
    reset_registry()
    raw2 = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        primary_key="story_id",
    )
    def dim_stories() -> ibis.Table:
        return raw2.select(story_id=_.item_id, score=_.score)

    with pytest.raises(ValueError, match="full_refresh=True"):
        materialize_model(con, dim_stories)


def test_scd2_snapshot_rejects_incremental_key_and_window(
    ducklake_con, make_raw_items
) -> None:
    con = ducklake_con[0]
    raw = make_raw_items()

    with pytest.raises(ValueError, match="cannot use incremental_key or lookback"):

        @model(
            db_schema="marts",
            materialized="scd2",
            scd2_mode="snapshot",
            incremental_key="updated_at",
            primary_key="story_id",
        )
        def bad_snapshot() -> ibis.Table:
            return raw.select(
                story_id=_.item_id, score=_.score, updated_at=_.updated_at
            )

    @model(
        db_schema="marts",
        materialized="scd2",
        scd2_mode="snapshot",
        primary_key="story_id",
    )
    def ok_snapshot() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score)

    with pytest.raises(ValueError, match="cannot run with an incremental window"):
        materialize_model(
            con,
            ok_snapshot,
            window=(
                datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            ),
        )


def test_scd2_null_valid_from_col_rolls_back(ducklake_con, make_raw_items) -> None:
    con = ducklake_con[0]
    con.execute("INSERT INTO raw.items VALUES (1, 'alice', 10, 'V1', NULL, 'story')")
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="scd2",
        scd2_mode="changes",
        primary_key="story_id",
        valid_from_col="updated_at",
    )
    def dim_null_ts() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score, updated_at=_.updated_at)

    stats = materialize_model(con, dim_null_ts)
    assert stats.rolled_back
    assert stats.null_counts["updated_at"] == 1
    assert stats.null_counts["valid_from"] == 1
    assert (
        con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'dim_null_ts'"
        ).fetchall()[0][0]
        == 0
    )


def test_model_rejects_inapplicable_mode_kwargs(make_raw_items) -> None:
    raw = make_raw_items()

    with pytest.raises(ValueError, match="cannot specify incremental_key or lookback"):

        @model(
            db_schema="marts",
            materialized="view",
            incremental_key="updated_at",
        )
        def bad_view() -> ibis.Table:
            return raw.select(story_id=_.item_id, updated_at=_.updated_at)

    with pytest.raises(ValueError, match="cannot specify incremental_key or lookback"):

        @model(
            db_schema="marts",
            materialized="table",
            lookback=timedelta(hours=1),
        )
        def bad_table() -> ibis.Table:
            return raw.select(story_id=_.item_id, updated_at=_.updated_at)

    with pytest.raises(ValueError, match="cannot specify incremental_strategy"):

        @model(
            db_schema="marts",
            materialized="table",
            incremental_strategy="delete_insert",
        )
        def bad_strategy() -> ibis.Table:
            return raw.select(story_id=_.item_id)

    with pytest.raises(ValueError, match="cannot specify scd2_mode"):

        @model(
            db_schema="marts",
            materialized="incremental",
            primary_key="story_id",
            tracked_columns=("score",),
        )
        def bad_tracked() -> ibis.Table:
            return raw.select(story_id=_.item_id, score=_.score)

    with pytest.raises(ValueError, match="cannot specify scd2_mode"):

        @model(
            db_schema="marts",
            materialized="table",
            valid_from_col="updated_at",
        )
        def bad_valid_from() -> ibis.Table:
            return raw.select(story_id=_.item_id, updated_at=_.updated_at)

    with pytest.raises(ValueError, match="cannot specify scd2_mode"):

        @model(
            db_schema="marts",
            materialized="incremental",
            primary_key="story_id",
            scd2_mode="snapshot",
        )
        def bad_scd2_mode() -> ibis.Table:
            return raw.select(story_id=_.item_id, score=_.score)
