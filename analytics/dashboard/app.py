import datetime
from pathlib import Path

import altair as alt
import duckdb
import polars as pl
import streamlit as st

st.set_page_config(
    page_title="HackerNews Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Define paths dynamically relative to app.py location
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "storage" / "orca.ducklake"


@st.cache_data
def get_metadata():
    con = duckdb.connect()
    files_dir = PROJECT_ROOT / "storage" / "orca.ducklake.files"
    con.execute(
        f"ATTACH 'ducklake:{DB_PATH}' AS orca (DATA_PATH '{files_dir.as_posix()}/', OVERRIDE_DATA_PATH true, READ_ONLY)"
    )
    try:
        # Get min/max dates
        dates = con.execute(
            "SELECT min(created_at), max(created_at) FROM orca.marts.stories"
        ).fetchone()

        if not dates or dates[0] is None or dates[1] is None:
            raise ValueError("No story records found in the database.")

        min_date = dates[0]
        max_date = dates[1]

        # Get top 50 authors for quick selection
        authors_res = con.execute(
            "SELECT author FROM orca.marts.stories GROUP BY author ORDER BY count(*) DESC LIMIT 50"
        )
        top_authors = [r[0] for r in authors_res.fetchall() if r[0] is not None]
    finally:
        con.close()
    return min_date, max_date, top_authors


# 3. Fetch Metadata
try:
    min_datetime, max_datetime, top_authors_list = get_metadata()
except Exception as e:  # noqa: BLE001
    st.error(f"⚠️ Failed to initialize dashboard metadata: {e}")
    st.info(
        "Please check that the DuckLake database files in `storage/` are populated and up to date."
    )
    st.stop()

# 3. Sidebar Filters
st.sidebar.title("🔍 Filters & Settings")

# Story Type Filter
story_type = st.sidebar.selectbox(
    "Story Type",
    ["All Stories", "Show HN / Ask HN Only", "Link Stories Only"],
)

# Date Filter (Slider)
date_range = st.sidebar.slider(
    "Date Range",
    min_value=min_datetime.date(),
    max_value=max_datetime.date(),
    value=(min_datetime.date(), max_datetime.date()),
    format="YYYY-MM-DD",
)

# Author Filtering
st.sidebar.subheader("✍️ Author Filter")
top_author_select = st.sidebar.selectbox(
    "Quick Select Top Author",
    ["None", *top_authors_list],
)
author_search = st.sidebar.text_input(
    "Search Author Name",
    value="" if top_author_select == "None" else top_author_select,
)

# Limit Slider
limit_n = st.sidebar.slider("Top Items Count", min_value=5, max_value=50, value=10)


# 4. Polars Data Loading with SQL
@st.cache_data
def get_dashboard_data(
    type_filter: str,
    start_date: datetime.date,
    end_date: datetime.date,
    author: str,
    limit: int,
):
    con = duckdb.connect()
    files_dir = PROJECT_ROOT / "storage" / "orca.ducklake.files"
    con.execute(
        f"ATTACH 'ducklake:{DB_PATH}' AS orca (DATA_PATH '{files_dir.as_posix()}/', OVERRIDE_DATA_PATH true, READ_ONLY)"
    )

    # Build where clause
    where_clauses = []
    where_clauses.append(f"created_at >= '{start_date} 00:00:00'")
    where_clauses.append(f"created_at <= '{end_date} 23:59:59'")

    if type_filter == "Show HN / Ask HN Only":
        where_clauses.append("(title LIKE 'Show HN:%' OR title LIKE 'Ask HN:%')")
    elif type_filter == "Link Stories Only":
        where_clauses.append("url IS NOT NULL")

    if author.strip():
        safe_author = author.strip().replace("'", "''")
        where_clauses.append(f"author = '{safe_author}'")

    where_part = "WHERE " + " AND ".join(where_clauses)

    try:
        # Query 1: KPIs
        q_kpi = f"""
        SELECT
          count(*) as story_count,
          coalesce(sum(score), 0) as total_score,
          coalesce(avg(score), 0.0) as avg_score,
          coalesce(max(score), 0) as max_score,
          coalesce(sum(comment_count), 0) as total_comments,
          coalesce(avg(comment_count), 0.0) as avg_comments,
          count(case when url is not null then 1 end) as link_story_count,
          count(case when title like 'Show HN:%' or title like 'Ask HN:%' then 1 end) as show_ask_count
        FROM orca.marts.stories
        {where_part}
        """
        df_kpi = pl.read_database(q_kpi, connection=con)

        # Query 2: Top stories by score
        q_score = f"""
        SELECT title, score as total_score FROM orca.marts.stories
        {where_part} ORDER BY score DESC LIMIT {limit}
        """
        df_score = pl.read_database(q_score, connection=con)

        # Query 3: Top stories by comments
        q_comments = f"""
        SELECT title, comment_count as total_comments FROM orca.marts.stories
        {where_part} ORDER BY comment_count DESC LIMIT {limit}
        """
        df_comments = pl.read_database(q_comments, connection=con)

        # Query 4: Daily stories trend
        q_stories_trend = f"""
        SELECT created_at::date as day_val, count(*) as story_count FROM orca.marts.stories
        {where_part} GROUP BY day_val ORDER BY day_val ASC
        """
        df_stories_trend = pl.read_database(q_stories_trend, connection=con)

        # Query 5: Daily comments trend
        q_comments_trend = f"""
        SELECT created_at::date as day_val, sum(comment_count) as total_comments FROM orca.marts.stories
        {where_part} GROUP BY day_val ORDER BY day_val ASC
        """
        df_comments_trend = pl.read_database(q_comments_trend, connection=con)

        # Query 6: Top authors
        q_authors = f"""
        SELECT author, count(*) as story_count, coalesce(sum(score), 0) as total_score FROM orca.marts.stories
        {where_part} GROUP BY author ORDER BY story_count DESC LIMIT {limit}
        """
        df_authors = pl.read_database(q_authors, connection=con)

    finally:
        con.close()

    return (
        df_kpi,
        df_score,
        df_comments,
        df_stories_trend,
        df_comments_trend,
        df_authors,
    )


# 5. Fetch Dashboard Data
with st.spinner("Executing analytical database queries..."):
    try:
        (
            main_kpi,
            top_stories_by_score,
            top_stories_by_comments,
            stories_by_day,
            comments_by_day,
            top_authors,
        ) = get_dashboard_data(
            story_type, date_range[0], date_range[1], author_search, limit_n
        )
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to query the HackerNews data warehouse: {e}")
        st.stop()

# 6. Extract metrics
if main_kpi.height > 0:
    story_count = main_kpi.select("story_count").item()
    total_score = main_kpi.select("total_score").item()
    avg_score = main_kpi.select("avg_score").item()
    max_score = main_kpi.select("max_score").item()
    total_comments = main_kpi.select("total_comments").item()
    avg_comments = main_kpi.select("avg_comments").item()
    link_story_count = main_kpi.select("link_story_count").item()
    show_ask_count = main_kpi.select("show_ask_count").item()
else:
    st.warning("No data found for the selected filters.")
    st.stop()

# 7. Render Dashboard UI
st.title("📈 HackerNews Analytics Dashboard")
st.caption(
    "A direct SQL analytical dashboard built using **Polars** dataframes, **DuckDB** / **DuckLake** storage, and **Altair** charts."
)

st.markdown("---")

# Metrics Row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Stories", f"{story_count:,}")
    st.metric("Link Stories", f"{link_story_count:,}")

with col2:
    st.metric("Total Score", f"{int(total_score) if total_score else 0:,}")
    st.metric("Max Score", f"{max_score if max_score else 0:,}")

with col3:
    st.metric("Total Comments", f"{int(total_comments) if total_comments else 0:,}")
    st.metric("Avg Comments / Story", f"{avg_comments:.1f}" if avg_comments else "0.0")

with col4:
    st.metric("Avg Score / Story", f"{avg_score:.1f}" if avg_score else "0.0")
    st.metric("Show / Ask HN Stories", f"{show_ask_count:,}")

st.markdown("---")

# Daily Trend Section
st.subheader("📅 Daily Stories & Comments Trends")
trend_col1, trend_col2 = st.columns(2)

with trend_col1:
    if (
        stories_by_day.height > 0
        and stories_by_day.select("day_val").null_count().item()
        != stories_by_day.height
    ):
        stories_chart = (
            alt
            .Chart(stories_by_day.to_pandas())
            .mark_area(
                line={"color": "#6366f1"},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color="#6366f1", offset=0),
                        alt.GradientStop(color="rgba(99, 102, 241, 0.1)", offset=1),
                    ],
                    x1=1,
                    x2=1,
                    y1=1,
                    y2=0,
                ),
            )
            .encode(
                x=alt.X("day_val:T", title="Date"),
                y=alt.Y("story_count:Q", title="Story Count"),
                tooltip=["day_val:T", "story_count:Q"],
            )
            .properties(height=300, title="Daily Stories Count")
        )
        st.altair_chart(stories_chart, width="stretch")
    else:
        st.info("No trend data available for stories.")

with trend_col2:
    if (
        comments_by_day.height > 0
        and comments_by_day.select("day_val").null_count().item()
        != comments_by_day.height
    ):
        comments_chart = (
            alt
            .Chart(comments_by_day.to_pandas())
            .mark_area(
                line={"color": "#10b981"},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color="#10b981", offset=0),
                        alt.GradientStop(color="rgba(16, 185, 129, 0.1)", offset=1),
                    ],
                    x1=1,
                    x2=1,
                    y1=1,
                    y2=0,
                ),
            )
            .encode(
                x=alt.X("day_val:T", title="Date"),
                y=alt.Y("total_comments:Q", title="Total Comments"),
                tooltip=["day_val:T", "total_comments:Q"],
            )
            .properties(height=300, title="Daily Comments Count")
        )
        st.altair_chart(comments_chart, width="stretch")
    else:
        st.info("No trend data available for comments.")

st.markdown("---")

# Top Items Section
breakdown_col1, breakdown_col2 = st.columns(2)

with breakdown_col1:
    st.subheader(f"🏆 Top {limit_n} Stories by Score")
    if (
        top_stories_by_score.height > 0
        and top_stories_by_score.select("title").null_count().item()
        != top_stories_by_score.height
    ):
        score_chart = (
            alt
            .Chart(top_stories_by_score.to_pandas())
            .mark_bar(color="#6366f1", cornerRadiusEnd=4)
            .encode(
                x=alt.X("total_score:Q", title="Score"),
                y=alt.Y(
                    "title:N", sort="-x", title=None, axis=alt.Axis(labelLimit=250)
                ),
                tooltip=["title:N", "total_score:Q"],
            )
            .properties(height=350)
        )
        st.altair_chart(score_chart, width="stretch")
    else:
        st.info("No data available for top stories by score.")

with breakdown_col2:
    st.subheader(f"💬 Top {limit_n} Stories by Comments")
    if (
        top_stories_by_comments.height > 0
        and top_stories_by_comments.select("title").null_count().item()
        != top_stories_by_comments.height
    ):
        comments_bar_chart = (
            alt
            .Chart(top_stories_by_comments.to_pandas())
            .mark_bar(color="#10b981", cornerRadiusEnd=4)
            .encode(
                x=alt.X("total_comments:Q", title="Comments"),
                y=alt.Y(
                    "title:N", sort="-x", title=None, axis=alt.Axis(labelLimit=250)
                ),
                tooltip=["title:N", "total_comments:Q"],
            )
            .properties(height=350)
        )
        st.altair_chart(comments_bar_chart, width="stretch")
    else:
        st.info("No data available for top stories by comments.")

st.markdown("---")

# Authors Section
st.subheader("👥 Author Analysis")
author_col1, author_col2 = st.columns([2, 1])

with author_col1:
    if (
        top_authors.height > 0
        and top_authors.select("author").null_count().item() != top_authors.height
    ):
        authors_chart = (
            alt
            .Chart(top_authors.to_pandas())
            .mark_bar(color="#f59e0b", cornerRadiusEnd=4)
            .encode(
                x=alt.X("author:N", sort="-y", title="Author"),
                y=alt.Y("story_count:Q", title="Story Count"),
                color=alt.Color(
                    "total_score:Q",
                    scale=alt.Scale(scheme="oranges"),
                    title="Total Score",
                ),
                tooltip=["author:N", "story_count:Q", "total_score:Q"],
            )
            .properties(
                height=350, title=f"Top {limit_n} Authors (by Story Count & Score)"
            )
        )
        st.altair_chart(authors_chart, width="stretch")
    else:
        st.info("No author data available.")

with author_col2:
    st.markdown("##### Detailed Author Metrics")
    if (
        top_authors.height > 0
        and top_authors.select("author").null_count().item() != top_authors.height
    ):
        st.dataframe(
            top_authors.to_pandas(),
            column_config={
                "author": "Author",
                "story_count": st.column_config.NumberColumn("Stories", format="%d"),
                "total_score": st.column_config.NumberColumn(
                    "Total Score", format="%d"
                ),
            },
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No table data available.")
