import datetime as dt
import threading

import polars as pl
import streamlit as st
from ibis import _

from analytics.model import comments, stories

_DB_LOCK = threading.Lock()
CACHE_TTL = 3600

st.set_page_config(
    page_title="HackerNews dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="auto",
)

WEEKDAY_ORDER = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

WEEKDAY_SHORT = {
    "Monday": "Mon",
    "Tuesday": "Tue",
    "Wednesday": "Wed",
    "Thursday": "Thu",
    "Friday": "Fri",
    "Saturday": "Sat",
    "Sunday": "Sun",
}

STORY_TYPES = [
    "All stories",
    "Link",
    "Show HN",
    "Ask HN",
    "Self-Post",
    "Tell HN",
    "Launch HN",
]


def _run_polars(query) -> pl.DataFrame:
    """Execute a BSL query under a lock so concurrent sessions share DuckDB safely."""
    with _DB_LOCK:
        return query.to_polars()


def _calendar_weekday_counts(start_date: dt.date, end_date: dt.date) -> dict[str, int]:
    """Count exact calendar occurrences of each weekday inside [start_date, end_date]."""
    total_days = (end_date - start_date).days + 1
    full_weeks, rem = divmod(total_days, 7)
    start_wd = start_date.weekday()
    names = list(WEEKDAY_ORDER.keys())
    return {
        names[i]: full_weeks + (1 if (i - start_wd) % 7 < rem else 0) for i in range(7)
    }


def _filter_stories(start_date, end_date, story_type: str, author: str):
    """Apply active sidebar filters to the stories semantic table."""
    query = stories.filter(_.day.between(start_date, end_date))
    if story_type and story_type != "All stories":
        query = query.filter(_.story_type == story_type)
    if author and author != "All":
        query = query.filter(_.author == author)
    return query


def _filter_comments(start_date, end_date, story_type: str, author: str):
    """Apply active sidebar filters to the joined comments semantic table."""
    query = comments.filter(_["comments.day"].between(start_date, end_date))
    if story_type and story_type != "All stories":
        query = query.filter(_["stories.story_type"] == story_type)
    if author and author != "All":
        query = query.filter(_["stories.author"] == author)
    return query


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_metadata():
    """Fetch dataset timestamp bounds and top submitters for filter defaults."""
    bounds = _run_polars(stories.aggregate("min_created_at", "max_created_at")).row(
        0, named=True
    )
    top_authors = _run_polars(
        stories
        .group_by("author")
        .aggregate("story_count")
        .order_by(_.story_count.desc())
        .limit(50)
    )["author"].to_list()
    return bounds["min_created_at"], bounds["max_created_at"], top_authors


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_story_kpi(start_date, end_date, story_type: str, author: str) -> dict:
    """Compute top-level KPI metrics for stories in the selected filter window."""
    return _run_polars(
        _filter_stories(start_date, end_date, story_type, author).aggregate(
            "story_count",
            "unique_author_count",
            "total_score",
            "avg_score",
            "median_score",
            "max_score",
            "total_comments",
            "avg_comments",
            "comments_per_point",
            "discussion_rate",
            "traction_rate",
        )
    ).row(0, named=True)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_trends(
    start_date, end_date, story_type: str, author: str, time_grain: str
) -> pl.DataFrame:
    """Fetch calendar-aligned daily (7-day rolling avg) or weekly story/comment trends."""
    filtered = _filter_stories(start_date, end_date, story_type, author)
    if time_grain == "Daily":
        daily_df = _run_polars(
            filtered
            .group_by("day")
            .aggregate("story_count", "total_comments")
            .order_by("day")
        ).with_columns(pl.col("day").cast(pl.Date))
        calendar_df = pl.DataFrame({
            "day": pl.date_range(start_date, end_date, interval="1d", eager=True)
        })
        return (
            calendar_df
            .join(daily_df, on="day", how="left")
            .with_columns(
                pl.col("story_count").fill_null(0),
                pl.col("total_comments").fill_null(0),
            )
            .with_columns(
                pl
                .col("story_count")
                .rolling_mean(window_size=7, min_samples=1)
                .alias("stories_7d_avg"),
                pl
                .col("total_comments")
                .rolling_mean(window_size=7, min_samples=1)
                .alias("comments_7d_avg"),
            )
        )
    return _run_polars(
        filtered
        .group_by("week")
        .aggregate("story_count", "total_comments")
        .order_by("week")
    ).with_columns(
        pl.col("story_count").fill_null(0),
        pl.col("total_comments").fill_null(0),
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_story_types_breakdown(
    start_date, end_date, story_type: str, author: str
) -> pl.DataFrame:
    """Aggregate story volume, score skew, discussion, and traction by story format."""
    return _run_polars(
        _filter_stories(start_date, end_date, story_type, author)
        .group_by("story_type")
        .aggregate(
            "story_count",
            "story_share",
            "avg_score",
            "median_score",
            "discussion_rate",
            "traction_rate",
            "avg_comments",
            "comments_per_point",
        )
        .order_by(_.story_count.desc())
    ).with_columns(
        (pl.col("story_share").fill_null(0.0) * 100).alias("story_share_pct"),
        (pl.col("discussion_rate").fill_null(0.0) * 100).alias("discussion_rate_pct"),
        (pl.col("traction_rate").fill_null(0.0) * 100).alias("traction_rate_pct"),
        pl.col("avg_score").fill_null(0.0),
        pl.col("median_score").fill_null(0.0),
        pl.col("avg_comments").fill_null(0.0),
        pl.col("comments_per_point").fill_null(0.0),
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_top_domains(
    start_date, end_date, story_type: str, author: str, limit_n: int
) -> pl.DataFrame:
    """Rank external domains by story volume and engagement."""
    return _run_polars(
        _filter_stories(start_date, end_date, story_type, author)
        .filter(_.domain.notnull())
        .group_by("domain")
        .aggregate("story_count", "avg_score", "comments_per_point")
        .order_by(_.story_count.desc())
        .limit(limit_n)
    ).with_columns(
        pl.col("avg_score").fill_null(0.0),
        pl.col("comments_per_point").fill_null(0.0),
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_seasonality(
    start_date, end_date, story_type: str, author: str
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Compute complete 24-hour UTC and calendar-normalized weekday seasonality."""
    filtered = _filter_stories(start_date, end_date, story_type, author)
    queried_hourly = _run_polars(
        filtered
        .group_by("hour_of_day")
        .aggregate("story_count", "avg_score", "avg_comments")
        .order_by("hour_of_day")
    ).with_columns(pl.col("hour_of_day").cast(pl.Int64))
    hourly_df = (
        pl
        .DataFrame({"hour_of_day": list(range(24))})
        .join(queried_hourly, on="hour_of_day", how="left")
        .with_columns(
            pl.col("story_count").fill_null(0),
            pl.col("avg_score").fill_null(0.0),
            pl.col("avg_comments").fill_null(0.0),
            pl.col("hour_of_day").cast(pl.String).str.zfill(2).alias("hour_label"),
        )
        .sort("hour_of_day")
    )

    queried_dow = _run_polars(
        filtered.group_by("day_of_week").aggregate(
            "story_count", "total_score", "avg_score", "avg_comments"
        )
    )
    cal_counts = _calendar_weekday_counts(start_date, end_date)
    dow_scaffold = pl.DataFrame({
        "day_of_week": list(WEEKDAY_ORDER.keys()),
        "day_short": [WEEKDAY_SHORT[d] for d in WEEKDAY_ORDER],
        "_cal_days": [cal_counts[d] for d in WEEKDAY_ORDER],
    })
    dow_df = (
        dow_scaffold
        .join(queried_dow, on="day_of_week", how="left")
        .with_columns(
            pl.col("story_count").fill_null(0),
            pl.col("total_score").fill_null(0),
            pl.col("avg_score").fill_null(0.0),
            pl.col("avg_comments").fill_null(0.0),
        )
        .with_columns(
            pl
            .when(pl.col("_cal_days") > 0)
            .then(pl.col("story_count") / pl.col("_cal_days"))
            .otherwise(0.0)
            .alias("avg_daily_stories"),
            pl
            .when(pl.col("_cal_days") > 0)
            .then(pl.col("total_score") / pl.col("_cal_days"))
            .otherwise(0.0)
            .alias("avg_daily_score"),
        )
        .drop("_cal_days")
    )
    return hourly_df, dow_df


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_comments_kpi(start_date, end_date, story_type: str, author: str) -> dict:
    """Compute top-level KPI metrics for ingested comments in the selected window."""
    return _run_polars(
        _filter_comments(start_date, end_date, story_type, author).aggregate(
            "comments.comment_count",
            "comments.unique_author_count",
            "comments.top_level_comment_count",
            "comments.top_level_rate",
            "comments.avg_comment_length",
            "comments.median_comment_length",
        )
    ).row(0, named=True)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_comments_by_story_type(
    start_date, end_date, story_type: str, author: str
) -> pl.DataFrame:
    """Break down matched comments by parent story format, excluding unmatched items."""
    return (
        _run_polars(
            _filter_comments(start_date, end_date, story_type, author)
            .filter(_["stories.story_id"].notnull())
            .group_by("stories.story_type")
            .aggregate(
                "comments.comment_count",
                "comments.comment_share",
                "comments.top_level_comment_count",
                "comments.top_level_rate",
                "comments.avg_comment_length",
                "comments.median_comment_length",
            )
            .order_by(_["comments.comment_count"].desc())
        )
        .rename({
            "stories.story_type": "story_type",
            "comments.comment_count": "comment_count",
            "comments.comment_share": "comment_share",
            "comments.top_level_comment_count": "top_level_comment_count",
            "comments.top_level_rate": "top_level_rate",
            "comments.avg_comment_length": "avg_comment_length",
            "comments.median_comment_length": "median_comment_length",
        })
        .with_columns(
            (pl.col("comment_share").fill_null(0.0) * 100).alias("comment_share_pct"),
            ((1.0 - pl.col("top_level_rate").fill_null(0.0)) * 100).alias(
                "nested_share_pct"
            ),
            pl.col("avg_comment_length").fill_null(0.0),
            pl.col("median_comment_length").fill_null(0.0),
        )
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_top_stories(
    start_date,
    end_date,
    story_type: str,
    author: str,
    sort_by: str,
    limit_n: int,
) -> pl.DataFrame:
    """Fetch top stories ranked by total score or total comments with HN links."""
    sort_expr = (
        _.total_score.desc() if sort_by == "total_score" else _.total_comments.desc()
    )
    return _run_polars(
        _filter_stories(start_date, end_date, story_type, author)
        .group_by("story_id", "title", "author", "story_type", "domain", "day")
        .aggregate("total_score", "total_comments")
        .order_by(sort_expr)
        .limit(limit_n)
    ).with_columns(
        (
            pl.lit("https://news.ycombinator.com/item?id=")
            + pl.col("story_id").cast(pl.String)
        ).alias("hn_url"),
        pl.col("domain").fill_null("—"),
        pl.col("day").cast(pl.Date),
        pl.col("total_score").fill_null(0),
        pl.col("total_comments").fill_null(0),
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_top_submitters(
    start_date, end_date, story_type: str, author: str, limit_n: int
) -> pl.DataFrame:
    """Fetch most prolific story submitters in the selected filter window."""
    return _run_polars(
        _filter_stories(start_date, end_date, story_type, author)
        .group_by("author")
        .aggregate("story_count", "total_score", "avg_score")
        .order_by(_.story_count.desc())
        .limit(limit_n)
    )


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def get_top_commenters(
    start_date, end_date, story_type: str, author: str, limit_n: int
) -> pl.DataFrame:
    """Fetch most active commenters and their nested reply share."""
    return (
        _run_polars(
            _filter_comments(start_date, end_date, story_type, author)
            .filter(_["comments.author"].notnull())
            .group_by("comments.author")
            .aggregate(
                "comments.comment_count",
                "comments.top_level_rate",
                "comments.avg_comment_length",
            )
            .order_by(_["comments.comment_count"].desc())
            .limit(limit_n)
        )
        .rename({
            "comments.author": "author",
            "comments.comment_count": "comment_count",
            "comments.top_level_rate": "top_level_rate",
            "comments.avg_comment_length": "avg_comment_length",
        })
        .with_columns(
            ((1.0 - pl.col("top_level_rate").fill_null(0.0)) * 100).alias(
                "nested_share_pct"
            ),
            pl.col("avg_comment_length").fill_null(0.0),
        )
    )


def _render_dual_axis_trend_chart(
    df: pl.DataFrame,
    x_col: str,
    stories_col: str,
    comments_col: str,
    stories_tooltip: str,
    comments_tooltip: str,
    show_points: bool = False,
) -> None:
    """Render a full-width dual-axis Vega-Lite trend chart for stories and comments."""
    tooltip = [
        {
            "field": x_col,
            "type": "temporal",
            "title": "Date",
            "format": "%Y-%m-%d",
        },
        {
            "field": stories_col,
            "type": "quantitative",
            "title": stories_tooltip,
            "format": ",.0f",
        },
        {
            "field": comments_col,
            "type": "quantitative",
            "title": comments_tooltip,
            "format": ",.0f",
        },
    ]
    spec = {
        "resolve": {"scale": {"y": "independent"}},
        "layer": [
            {
                "mark": {"type": "line", "strokeWidth": 2.5, "point": show_points},
                "encoding": {
                    "x": {
                        "field": x_col,
                        "type": "temporal",
                        "axis": {"title": None, "labelFlush": True},
                    },
                    "y": {
                        "field": stories_col,
                        "type": "quantitative",
                        "axis": {
                            "title": "Stories",
                            "titleColor": "#18181B",
                            "labelColor": "#18181B",
                            "orient": "left",
                            "grid": True,
                        },
                    },
                    "color": {
                        "datum": "Stories",
                        "scale": {
                            "domain": ["Stories", "Comments"],
                            "range": ["#18181B", "#D95D1E"],
                        },
                        "legend": {
                            "orient": "top",
                            "direction": "horizontal",
                            "title": None,
                        },
                    },
                    "tooltip": tooltip,
                },
            },
            {
                "mark": {"type": "line", "strokeWidth": 2.5, "point": show_points},
                "encoding": {
                    "x": {"field": x_col, "type": "temporal"},
                    "y": {
                        "field": comments_col,
                        "type": "quantitative",
                        "axis": {
                            "title": "Comments",
                            "titleColor": "#D95D1E",
                            "labelColor": "#D95D1E",
                            "orient": "right",
                            "grid": False,
                        },
                    },
                    "color": {"datum": "Comments"},
                    "tooltip": tooltip,
                },
            },
        ],
    }
    st.vega_lite_chart(df, spec, width="stretch", height=300)


def _render_weekday_bar_chart(
    df: pl.DataFrame,
    y_col: str,
    tooltip_label: str,
    color: str,
    height: int = 240,
    fmt: str = ",.0f",
) -> None:
    """Render a weekday bar chart with upright Mon-Sun x-axis labels."""
    spec = {
        "mark": {
            "type": "bar",
            "color": color,
            "cornerRadiusTopLeft": 2,
            "cornerRadiusTopRight": 2,
        },
        "encoding": {
            "x": {
                "field": "day_short",
                "type": "nominal",
                "sort": list(WEEKDAY_SHORT.values()),
                "axis": {"title": None, "labelAngle": 0},
            },
            "y": {
                "field": y_col,
                "type": "quantitative",
                "axis": {"title": None},
            },
            "tooltip": [
                {"field": "day_of_week", "type": "nominal", "title": "Day"},
                {
                    "field": y_col,
                    "type": "quantitative",
                    "title": tooltip_label,
                    "format": fmt,
                },
            ],
        },
    }
    st.vega_lite_chart(df, spec, width="stretch", height=height)


def _render_breakout_stories_table(df: pl.DataFrame, highlight_col: str) -> None:
    """Render a full-width breakout stories dataframe with clickable HN links."""
    max_score_val = max(int(df["total_score"].max() or 1), 1)
    max_comments_val = max(int(df["total_comments"].max() or 1), 1)

    score_col_cfg = (
        st.column_config.ProgressColumn(
            "Score",
            format="localized",
            min_value=0,
            max_value=max_score_val,
            width=100,
        )
        if highlight_col == "total_score"
        else st.column_config.NumberColumn("Score", format="localized", width=75)
    )
    comments_col_cfg = (
        st.column_config.ProgressColumn(
            "Comments",
            format="localized",
            min_value=0,
            max_value=max_comments_val,
            width=105,
        )
        if highlight_col == "total_comments"
        else st.column_config.NumberColumn("Comments", format="localized", width=85)
    )

    st.dataframe(
        df.select(
            "title",
            "hn_url",
            "story_type",
            "domain",
            "author",
            "day",
            "total_score",
            "total_comments",
        ),
        column_config={
            "title": st.column_config.TextColumn("Story", width=310),
            "hn_url": st.column_config.LinkColumn("HN", display_text="Open", width=52),
            "story_type": st.column_config.TextColumn("Format", width=78),
            "domain": st.column_config.TextColumn("Domain", width=135),
            "author": st.column_config.TextColumn("Author", width=112),
            "day": st.column_config.DateColumn("Date", format="YYYY-MM-DD", width=92),
            "total_score": score_col_cfg,
            "total_comments": comments_col_cfg,
        },
        hide_index=True,
        width="stretch",
    )


def _render_domains_section(domains_df: pl.DataFrame, limit_n: int) -> None:
    """Render top linked domains with volume bar chart and metrics table tabs."""
    st.markdown(f"**Top {limit_n} linked domains**")
    if domains_df.is_empty():
        st.info("No external link domains match the current filters.")
        return
    tab_dom_chart, tab_dom_table = st.tabs(["Volume chart", "Domain metrics"])
    with tab_dom_chart:
        st.bar_chart(
            domains_df,
            x="domain",
            y="story_count",
            x_label="",
            y_label="Stories",
            horizontal=True,
            sort="-story_count",
            color="#18181B",
            height=280,
        )
    with tab_dom_table:
        st.dataframe(
            domains_df,
            column_config={
                "domain": "Domain",
                "story_count": st.column_config.NumberColumn(
                    "Stories", format="localized"
                ),
                "avg_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
                "comments_per_point": st.column_config.NumberColumn(
                    "Comments / pt", format="%.2f"
                ),
            },
            hide_index=True,
            width="stretch",
        )


def _render_commenters_section(
    top_commenters_df: pl.DataFrame, limit_n: int, author: str
) -> None:
    """Render top commenters table with context-aware heading."""
    heading = (
        f"🗣️ Top {limit_n} commenters"
        if author == "All"
        else f"🗣️ Top {limit_n} commenters on {author}'s stories"
    )
    st.subheader(heading)
    if top_commenters_df.is_empty():
        st.info("No commenters match the current filters.")
        return
    st.dataframe(
        top_commenters_df.select(
            "author",
            "comment_count",
            "nested_share_pct",
            "avg_comment_length",
        ),
        column_config={
            "author": "Commenter",
            "comment_count": st.column_config.NumberColumn(
                "Comments", format="localized"
            ),
            "nested_share_pct": st.column_config.NumberColumn(
                "Nested %", format="%.1f%%"
            ),
            "avg_comment_length": st.column_config.NumberColumn(
                "Avg chars", format="%.0f"
            ),
        },
        hide_index=True,
        width="stretch",
    )


min_datetime, max_datetime, top_authors_list = get_metadata()

if min_datetime is None or max_datetime is None:
    st.info("No stories available in the warehouse yet.")
    st.stop()

min_date, max_date = min_datetime.date(), max_datetime.date()

# Sidebar Filters
st.sidebar.title("🔍 Story filters")
story_type = st.sidebar.selectbox("Story type", STORY_TYPES)
if min_date == max_date:
    date_range = (min_date, max_date)
    st.sidebar.caption(f"Date range: {min_date}")
else:
    date_range = st.sidebar.slider(
        "Date range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="YYYY-MM-DD",
    )
author = (
    st.sidebar.selectbox(
        "Story submitter",
        ["All", *top_authors_list],
        accept_new_options=True,
        help="Filter stories (and discussions on those stories) by submitter username.",
    )
    or "All"
)
time_grain = (
    st.sidebar.segmented_control(
        "Trend granularity",
        ["Daily", "Weekly"],
        default="Daily",
    )
    or "Daily"
)
limit_n = st.sidebar.slider("Top items count", min_value=5, max_value=50, value=10)

st.sidebar.divider()
st.sidebar.caption(f"Latest story: {max_datetime.strftime('%Y-%m-%d %H:%M UTC')}")
st.sidebar.caption(
    "[Dagster UI](https://orca-datawarehouse.dev/orchestration/) · "
    "[dbt docs](https://orca-datawarehouse.dev/transformation/) · "
    "[GitHub](https://github.com/mathisdrn/orca)"
)

start_date, end_date = date_range
kpi = get_story_kpi(start_date, end_date, story_type, author)
story_count = kpi["story_count"] or 0

if story_count == 0:
    st.warning("No stories found for the selected filters.")
    st.stop()

window_days = (end_date - start_date).days + 1
unique_authors = kpi["unique_author_count"] or 0
total_score = kpi["total_score"] or 0
avg_score = kpi["avg_score"] or 0.0
total_comments = kpi["total_comments"] or 0
comments_per_point = kpi["comments_per_point"] or 0.0
median_score = kpi["median_score"] or 0.0
discussion_rate_pct = (kpi["discussion_rate"] or 0.0) * 100
traction_rate_pct = (kpi["traction_rate"] or 0.0) * 100

# Header
st.title("HackerNews dashboard")
st.caption(
    f"Exploring **{story_count:,}** stories across **{window_days:,}** days "
    f"(**{start_date}** to **{end_date}**) — powered by **Boring Semantic Layer**, **Ibis**, and **DuckLake**."
)

# -----------------------------------------------------------------------------
# Overview KPIs & trends
# -----------------------------------------------------------------------------

row1_c1, row1_c2, row1_c3, row1_c4 = st.columns(4)
row1_c1.metric("Stories", f"{story_count:,}")
row1_c2.metric("Unique submitters", f"{unique_authors:,}")
row1_c3.metric("Total score", f"{total_score:,}")
row1_c4.metric(
    "Story comments",
    f"{total_comments:,}",
    help="Sum of comment counts reported on stories created in this window.",
)

row2_c1, row2_c2, row2_c3, row2_c4 = st.columns(4)
row2_c1.metric(
    "Avg score / story",
    f"{avg_score:.1f}",
    help=f"Mean points per story (median {median_score:.0f} — HackerNews scores are heavily right-skewed).",
)
row2_c2.metric(
    "Discussion rate",
    f"{discussion_rate_pct:.1f}%",
    help="Share of submitted stories that received at least one comment.",
)
row2_c3.metric(
    "Traction rate (≥10 pts)",
    f"{traction_rate_pct:.1f}%",
    help="Share of submitted stories reaching at least 10 points.",
)
row2_c4.metric(
    "Comments / point",
    f"{comments_per_point:.2f}",
    help="Total story comments divided by total score — a proxy for debate intensity.",
)

trends_df = get_trends(start_date, end_date, story_type, author, time_grain)
hourly_df, dow_df = get_seasonality(start_date, end_date, story_type, author)

if time_grain == "Daily":
    st.markdown("**Stories and comments trend (7-day average)**")
    _render_dual_axis_trend_chart(
        trends_df,
        "day",
        "stories_7d_avg",
        "comments_7d_avg",
        "Stories (7d avg)",
        "Comments (7d avg)",
        show_points=len(trends_df) < 7,
    )
else:
    st.markdown("**Weekly stories and comments trend**")
    _render_dual_axis_trend_chart(
        trends_df,
        "week",
        "story_count",
        "total_comments",
        "Weekly stories",
        "Weekly comments",
        show_points=True,
    )
    if len(trends_df) > 1:
        st.caption(
            "Note: the first and last weekly buckets may be partial if the selected date range starts or ends mid-week."
        )

if not dow_df.is_empty():
    max_daily_stories = float(dow_df["avg_daily_stories"].max() or 0.0)
    max_daily_score = float(dow_df["avg_daily_score"].max() or 0.0)
    stories_fmt = ",.1f" if max_daily_stories < 10 else ",.0f"
    score_fmt = ",.1f" if max_daily_score < 10 else ",.0f"

    dow_vol_col, dow_pts_col = st.columns(2)
    with dow_vol_col:
        st.markdown("**Average stories per day of week**")
        _render_weekday_bar_chart(
            dow_df,
            "avg_daily_stories",
            "Avg stories / day",
            "#18181B",
            height=240,
            fmt=stories_fmt,
        )
    with dow_pts_col:
        st.markdown("**Average points per day of week**")
        _render_weekday_bar_chart(
            dow_df,
            "avg_daily_score",
            "Avg points / day",
            "#D95D1E",
            height=240,
            fmt=score_fmt,
        )

# -----------------------------------------------------------------------------
# What gets submitted vs. what resonates
# -----------------------------------------------------------------------------
st.divider()
st.header("What gets submitted vs. what resonates")

story_types_df = get_story_types_breakdown(start_date, end_date, story_type, author)
domains_df = get_top_domains(start_date, end_date, story_type, author, limit_n)

domain_callout = (
    f" Among external links, **`{domains_df['domain'][0]}`** leads submissions "
    f"with **{domains_df['story_count'][0]:,}** stories (avg **{domains_df['avg_score'][0]:.1f}** pts)."
    if not domains_df.is_empty()
    else ""
)

if len(story_types_df) > 1:
    vol_leader = story_types_df.sort("story_count", descending=True).row(0, named=True)
    score_leader = story_types_df.sort("avg_score", descending=True).row(0, named=True)
    debate_leader = story_types_df.sort("comments_per_point", descending=True).row(
        0, named=True
    )
    st.markdown(
        f"**{vol_leader['story_type']}** drives **{vol_leader['story_share_pct']:.1f}%** of volume, "
        f"while **{score_leader['story_type']}** earns the highest average score (**{score_leader['avg_score']:.1f}** pts, "
        f"median **{score_leader['median_score']:.0f}**) and **{debate_leader['story_type']}** sparks the most debate "
        f"(**{debate_leader['comments_per_point']:.2f}** comments/pt).{domain_callout}"
    )
else:
    only_type = story_types_df.row(0, named=True)
    st.markdown(
        f"**{only_type['story_type']}** stories average **{only_type['avg_score']:.1f}** points "
        f"(median **{only_type['median_score']:.0f}**) and **{only_type['avg_comments']:.1f}** comments "
        f"(**{only_type['comments_per_point']:.2f}** comments/pt).{domain_callout}"
    )

st.markdown("**Engagement by story format**")
st.dataframe(
    story_types_df.select(
        "story_type",
        "story_count",
        "story_share_pct",
        "avg_score",
        "median_score",
        "discussion_rate_pct",
        "traction_rate_pct",
        "avg_comments",
        "comments_per_point",
    ),
    column_config={
        "story_type": "Format",
        "story_count": st.column_config.NumberColumn("Stories", format="localized"),
        "story_share_pct": st.column_config.NumberColumn("Share", format="%.1f%%"),
        "avg_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
        "median_score": st.column_config.NumberColumn("Median score", format="%.0f"),
        "discussion_rate_pct": st.column_config.NumberColumn(
            "Discussion rate", format="%.1f%%"
        ),
        "traction_rate_pct": st.column_config.NumberColumn(
            "Traction ≥10 pts", format="%.1f%%"
        ),
        "avg_comments": st.column_config.NumberColumn("Avg comments", format="%.1f"),
        "comments_per_point": st.column_config.NumberColumn(
            "Comments / pt", format="%.2f"
        ),
    },
    hide_index=True,
    width="stretch",
)

if len(story_types_df) > 1:
    fmt_col, dom_col = st.columns(2)
    with fmt_col:
        st.markdown("**Average comments per point by format**")
        st.bar_chart(
            story_types_df,
            x="story_type",
            y="comments_per_point",
            x_label="",
            y_label="Comments / point",
            horizontal=True,
            sort="-comments_per_point",
            color="#D95D1E",
            height=280,
        )
    with dom_col:
        _render_domains_section(domains_df, limit_n)
else:
    _render_domains_section(domains_df, limit_n)

# -----------------------------------------------------------------------------
# When HackerNews reads and votes (UTC)
# -----------------------------------------------------------------------------
st.divider()
st.header("When HackerNews reads and votes (UTC)")

active_hours = hourly_df.filter(pl.col("story_count") > 0)
active_dows = dow_df.filter(pl.col("story_count") > 0)

if active_hours.is_empty() or active_dows.is_empty():
    st.info("No seasonality data matches the current filters.")
else:
    busiest_hour = active_hours.sort("story_count", descending=True).row(0, named=True)
    best_score_hour = active_hours.sort("avg_score", descending=True).row(0, named=True)
    best_dow = active_dows.sort("avg_score", descending=True).row(0, named=True)

    st.markdown(
        f"Submission volume peaks at **{busiest_hour['hour_of_day']:02d}:00 UTC** "
        f"(**{busiest_hour['story_count']:,}** stories), while stories posted around "
        f"**{best_score_hour['hour_of_day']:02d}:00 UTC** achieve the highest average score "
        f"(**{best_score_hour['avg_score']:.1f}** pts). Across the week, **{best_dow['day_of_week']}** "
        f"posts average the highest score (**{best_dow['avg_score']:.1f}** pts)."
    )

    hr_vol_col, hr_score_col = st.columns(2)
    with hr_vol_col:
        st.markdown("**Hourly submission volume (UTC)**")
        st.bar_chart(
            hourly_df,
            x="hour_label",
            y="story_count",
            x_label="UTC hour",
            y_label="",
            sort=False,
            color="#18181B",
            height=240,
        )
    with hr_score_col:
        st.markdown("**Hourly average score (UTC)**")
        st.bar_chart(
            hourly_df,
            x="hour_label",
            y="avg_score",
            x_label="UTC hour",
            y_label="",
            sort=False,
            color="#D95D1E",
            height=240,
        )

    dow_chart_col, dow_table_col = st.columns(2)
    with dow_chart_col:
        st.markdown("**Average score by day of week**")
        _render_weekday_bar_chart(
            dow_df,
            "avg_score",
            "Avg score",
            "#D95D1E",
            height=260,
            fmt=",.1f",
        )
    with dow_table_col:
        st.markdown("**Weekday performance summary**")
        st.dataframe(
            dow_df.select("day_of_week", "story_count", "avg_score", "avg_comments"),
            column_config={
                "day_of_week": "Day",
                "story_count": st.column_config.NumberColumn(
                    "Stories", format="localized"
                ),
                "avg_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
                "avg_comments": st.column_config.NumberColumn(
                    "Avg comments", format="%.1f"
                ),
            },
            hide_index=True,
            height=280,
            width="stretch",
        )

# -----------------------------------------------------------------------------
# Inside the discussion threads
# -----------------------------------------------------------------------------
st.divider()
st.header("Inside the discussion threads")

c_kpi = get_comments_kpi(start_date, end_date, story_type, author)
total_c = c_kpi["comments.comment_count"] or 0

if total_c == 0:
    st.info("No comments match the current filters.")
else:
    unique_commenters = c_kpi["comments.unique_author_count"] or 0
    top_level_rate = c_kpi["comments.top_level_rate"] or 0.0
    nested_share_pct = (1.0 - top_level_rate) * 100
    avg_c_len = c_kpi["comments.avg_comment_length"] or 0.0
    median_c_len = c_kpi["comments.median_comment_length"] or 0.0

    ck1, ck2, ck3, ck4 = st.columns(4)
    ck1.metric(
        "Ingested comments",
        f"{total_c:,}",
        help=(
            "Individual comment records posted in this window (differs from the overview "
            "story comment counts due to comments on pre-window stories and late arrivals "
            "after story snapshots)."
        ),
    )
    ck2.metric(
        "Unique commenters",
        f"{unique_commenters:,}",
    )
    ck3.metric(
        "Nested reply share",
        f"{nested_share_pct:.1f}%",
        help="Share of comments that reply to another comment rather than directly to the story.",
    )
    ck4.metric(
        "Avg comment length",
        f"{avg_c_len:.0f} chars",
        help=f"Raw character length of ingested comment text, including HTML markup (median {median_c_len:.0f} chars).",
    )

    c_by_type_df = get_comments_by_story_type(start_date, end_date, story_type, author)

    if not c_by_type_df.is_empty():
        matched_c = int(c_by_type_df["comment_count"].sum())
        unmatched_c = total_c - matched_c

        if len(c_by_type_df) > 1:
            longest_c_type = c_by_type_df.sort(
                "avg_comment_length", descending=True
            ).row(0, named=True)
            deepest_c_type = c_by_type_df.sort("nested_share_pct", descending=True).row(
                0, named=True
            )
            st.markdown(
                f"**{nested_share_pct:.1f}%** of the **{total_c:,}** ingested comments are nested replies inside threads, "
                f"averaging **{avg_c_len:.0f}** characters (median **{median_c_len:.0f}**). "
                f"**{longest_c_type['story_type']}** threads draw the longest responses "
                f"(avg **{longest_c_type['avg_comment_length'] or 0.0:.0f}** chars), while **{deepest_c_type['story_type']}** "
                f"discussions go deepest (**{deepest_c_type['nested_share_pct'] or 0.0:.1f}%** nested replies)."
            )
        else:
            only_c_type = c_by_type_df.row(0, named=True)
            st.markdown(
                f"**{nested_share_pct:.1f}%** of the **{total_c:,}** ingested comments on "
                f"**{only_c_type['story_type']}** stories are nested replies inside threads, "
                f"averaging **{avg_c_len:.0f}** characters (median **{median_c_len:.0f}**)."
            )

        if unmatched_c > 0:
            st.caption(
                f"Format breakdown covers {matched_c:,} comments linked to stories in this dataset "
                f"({unmatched_c:,} additional comments belong to pre-window stories or polls)."
            )

        if len(c_by_type_df) > 1:
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                st.markdown("**Average comment length by story format**")
                st.bar_chart(
                    c_by_type_df,
                    x="story_type",
                    y="avg_comment_length",
                    x_label="",
                    y_label="Average characters",
                    horizontal=True,
                    sort="-avg_comment_length",
                    color="#18181B",
                    height=260,
                )
            with c_col2:
                st.markdown("**Nested reply share by story format**")
                st.bar_chart(
                    c_by_type_df,
                    x="story_type",
                    y="nested_share_pct",
                    x_label="",
                    y_label="Nested replies (%)",
                    horizontal=True,
                    sort="-nested_share_pct",
                    color="#D95D1E",
                    height=260,
                )

        st.markdown("**Comment breakdown by story format**")
        st.dataframe(
            c_by_type_df.select(
                "story_type",
                "comment_count",
                "comment_share_pct",
                "top_level_comment_count",
                "nested_share_pct",
                "avg_comment_length",
                "median_comment_length",
            ),
            column_config={
                "story_type": "Format",
                "comment_count": st.column_config.NumberColumn(
                    "Comments", format="localized"
                ),
                "comment_share_pct": st.column_config.NumberColumn(
                    "Share", format="%.1f%%"
                ),
                "top_level_comment_count": st.column_config.NumberColumn(
                    "Top-level", format="localized"
                ),
                "nested_share_pct": st.column_config.NumberColumn(
                    "Nested share", format="%.1f%%"
                ),
                "avg_comment_length": st.column_config.NumberColumn(
                    "Avg chars", format="%.0f"
                ),
                "median_comment_length": st.column_config.NumberColumn(
                    "Median chars", format="%.0f"
                ),
            },
            hide_index=True,
            width="stretch",
        )

# -----------------------------------------------------------------------------
# Breakout stories and community voices
# -----------------------------------------------------------------------------
st.divider()
st.header("Breakout stories and community voices")

tab_score, tab_comments = st.tabs([
    f"🏆 Top {limit_n} by score",
    f"💬 Top {limit_n} by comments",
])
with tab_score:
    top_by_score = get_top_stories(
        start_date, end_date, story_type, author, "total_score", limit_n
    )
    _render_breakout_stories_table(top_by_score, "total_score")
with tab_comments:
    top_by_comments = get_top_stories(
        start_date, end_date, story_type, author, "total_comments", limit_n
    )
    _render_breakout_stories_table(top_by_comments, "total_comments")

top_commenters_df = get_top_commenters(
    start_date, end_date, story_type, author, limit_n
)

if author == "All":
    top_submitters_df = get_top_submitters(
        start_date, end_date, story_type, author, limit_n
    )
    voice_col1, voice_col2 = st.columns(2)
    with voice_col1:
        st.subheader(f"✍️ Top {limit_n} story submitters")
        st.dataframe(
            top_submitters_df,
            column_config={
                "author": "Author",
                "story_count": st.column_config.NumberColumn(
                    "Stories", format="localized"
                ),
                "total_score": st.column_config.NumberColumn(
                    "Total score", format="localized"
                ),
                "avg_score": st.column_config.NumberColumn("Avg score", format="%.1f"),
            },
            hide_index=True,
            width="stretch",
        )
    with voice_col2:
        _render_commenters_section(top_commenters_df, limit_n, author)
else:
    _render_commenters_section(top_commenters_df, limit_n, author)
