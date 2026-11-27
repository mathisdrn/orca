import dagster as dg
import ibis
from ibis import _

from orchestration.assets import ModelRunConfig, build_model_asset
from orchestration.resources import DuckLakeResource
from transformation.engine.compiler import model
from transformation.engine.executor import materialize_model


def test_table_column_constraints_reflect_not_null_and_scd2(make_raw_items) -> None:
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="scd2",
        scd2_mode="changes",
        primary_key="story_id",
        valid_from_col="updated_at",
    )
    def dim_items() -> ibis.Table:
        return raw.select(
            story_id=_.item_id,
            author=_.author,
            score=_.score,
            updated_at=_.updated_at,
        )

    asset_def = build_model_asset(dim_items)
    col_schema = asset_def.metadata_by_key[dg.AssetKey(["marts", "dim_items"])][
        "dagster/column_schema"
    ]
    constraints = {col.name: col.constraints for col in col_schema.columns}
    assert constraints["story_id"].nullable is False
    assert constraints["updated_at"].nullable is False
    assert constraints["valid_from"].nullable is False
    assert constraints["is_current"].nullable is False
    assert constraints["author"].nullable is True
    assert constraints["story_id"].unique is False


def test_model_run_config_full_refresh(ducklake_con, make_raw_items) -> None:
    con, catalog, files_dir = ducklake_con
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 10, 'S1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')"
    )
    con.close()

    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="merge",
        incremental_key="updated_at",
        primary_key="story_id",
    )
    def cfg_stories() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score, updated_at=_.updated_at)

    asset_def = build_model_asset(cfg_stories)
    resource = DuckLakeResource(
        catalog_path=catalog.as_posix(),
        data_path=f"{files_dir.as_posix()}/",
    )

    res1 = dg.materialize([asset_def], resources={"ducklake": resource})
    assert res1.success

    with resource.connect() as mut_con:
        mut_con.execute("DELETE FROM marts.cfg_stories")

    res2 = dg.materialize(
        [asset_def],
        resources={"ducklake": resource},
        run_config=dg.RunConfig(
            ops={"marts__cfg_stories": ModelRunConfig(full_refresh=True)}
        ),
    )
    assert res2.success
    with resource.connect() as verify_con:
        assert (
            verify_con.execute("SELECT count(*) FROM marts.cfg_stories").fetchall()[0][
                0
            ]
            == 1
        )


def test_partitioned_asset_single_and_range_window(
    ducklake_con, make_raw_items
) -> None:
    con, catalog, files_dir = ducklake_con
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'D1', TIMESTAMPTZ '2026-07-01 10:00:00+00', 'story'),
            (2, 'bob', 20, 'D2', TIMESTAMPTZ '2026-07-02 10:00:00+00', 'story'),
            (3, 'carol', 30, 'D3', TIMESTAMPTZ '2026-07-03 10:00:00+00', 'story')
        """
    )
    con.close()

    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="incremental",
        incremental_strategy="delete_insert",
        incremental_key="updated_date",
    )
    def part_stories() -> ibis.Table:
        return raw.select(
            story_id=_.item_id,
            score=_.score,
            updated_date=_.updated_at.date(),
        )

    partitions_def = dg.DailyPartitionsDefinition(
        start_date="2026-07-01", timezone="UTC"
    )
    asset_def = build_model_asset(part_stories, partitions_def=partitions_def)
    resource = DuckLakeResource(
        catalog_path=catalog.as_posix(),
        data_path=f"{files_dir.as_posix()}/",
    )

    # Initial seed with July 1 single partition
    res1 = dg.materialize(
        [asset_def],
        resources={"ducklake": resource},
        partition_key="2026-07-01",
    )
    assert res1.success

    # Multi-partition range backfill for July 2..July 3
    ctx = dg.build_asset_context(
        partition_key_range=dg.PartitionKeyRange("2026-07-02", "2026-07-03"),
        resources={"ducklake": resource},
    )
    events = list(asset_def(ctx, config=ModelRunConfig()))
    mat_events = [e for e in events if isinstance(e, dg.MaterializeResult)]
    assert len(mat_events) == 1
    assert mat_events[0].metadata["rows_affected"] == 2
    assert mat_events[0].metadata["dagster/row_count"] == 3


def test_dagster_precommit_rollback_no_phantom_materialization(
    ducklake_con, make_raw_items
) -> None:
    con, catalog, files_dir = ducklake_con
    con.execute(
        """
        INSERT INTO raw.items VALUES
            (1, 'alice', 10, 'A', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story'),
            (1, 'alice', 20, 'B', TIMESTAMPTZ '2026-07-02 00:00:00+00', 'story')
        """
    )
    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="table",
        primary_key=("story_id", "updated_at"),
        not_null=("author",),
    )
    def comp_stories() -> ibis.Table:
        return raw.select(
            story_id=_.item_id, updated_at=_.updated_at, author=_.author, score=_.score
        )

    ok_stats = materialize_model(con, comp_stories)
    assert not ok_stats.rolled_back
    assert ok_stats.duplicate_counts[("story_id", "updated_at")] == 0

    # Introduce NULL author -> check must fail, rollback DuckLake snapshot, and preserve old rows
    con.execute(
        "INSERT INTO raw.items VALUES (2, NULL, 30, 'Bad', TIMESTAMPTZ '2026-07-03 00:00:00+00', 'story')"
    )
    snaps_before = len(con.execute("FROM orca.snapshots()").fetchall())
    con.close()

    asset_def = build_model_asset(comp_stories)
    resource = DuckLakeResource(
        catalog_path=catalog.as_posix(),
        data_path=f"{files_dir.as_posix()}/",
    )
    res = dg.materialize(
        [asset_def],
        resources={"ducklake": resource},
        raise_on_error=False,
    )
    assert not res.success
    assert res.get_asset_materialization_events() == []
    check_evals = res.get_asset_check_evaluations()
    assert any(
        ev.check_name == "not_null_comp_stories_author" and not ev.passed
        for ev in check_evals
    )

    with resource.connect() as verify_con:
        snaps_after = len(verify_con.execute("FROM orca.snapshots()").fetchall())
        assert snaps_after == snaps_before
        assert (
            verify_con.execute("SELECT count(*) FROM marts.comp_stories").fetchall()[0][
                0
            ]
            == 2
        )


def test_static_partitioned_asset_ignores_time_window(
    ducklake_con, make_raw_items
) -> None:
    con, catalog, files_dir = ducklake_con
    con.execute(
        "INSERT INTO raw.items VALUES (1, 'alice', 10, 'S1', TIMESTAMPTZ '2026-07-01 00:00:00+00', 'story')"
    )
    con.close()

    raw = make_raw_items()

    @model(
        db_schema="marts",
        materialized="table",
        primary_key="story_id",
    )
    def static_stories() -> ibis.Table:
        return raw.select(story_id=_.item_id, score=_.score)

    partitions_def = dg.StaticPartitionsDefinition(["us", "eu"])
    asset_def = build_model_asset(static_stories, partitions_def=partitions_def)
    resource = DuckLakeResource(
        catalog_path=catalog.as_posix(),
        data_path=f"{files_dir.as_posix()}/",
    )
    res = dg.materialize(
        [asset_def],
        resources={"ducklake": resource},
        partition_key="us",
    )
    assert res.success
    with resource.connect() as verify_con:
        assert (
            verify_con.execute("SELECT count(*) FROM marts.static_stories").fetchall()[
                0
            ][0]
            == 1
        )
