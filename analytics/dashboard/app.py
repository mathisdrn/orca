import streamlit as st
from ibis import _

from analytics.model import stories

st.set_page_config(
    page_title="HackerNews Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 1. Fetch Metadata
@st.cache_data
def get_metadata():
    bounds = (
        stories
        .aggregate("min_created_at", "max_created_at")
        .to_polars()
        .row(0, named=True)
    )
    top_authors = (
        stories
        .group_by("author")
        .aggregate("story_count")
        .order_by(_.story_count.desc())
        .limit(50)
        .to_polars()["author"]
        .to_list()
    )
    return bounds["min_created_at"], bounds["max_created_at"], top_authors


min_datetime, max_datetime, top_authors_list = get_metadata()

# 2. Sidebar Filters
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
author = st.sidebar.selectbox(
    "Author",
    ["All", *top_authors_list],
    accept_new_options=True,
)

# Limit Slider
limit_n = st.sidebar.slider("Top Items Count", min_value=5, max_value=50, value=10)

# 3. Filter Semantic Model
filtered = stories.filter(_.day.between(date_range[0], date_range[1]))
if story_type == "Show HN / Ask HN Only":
    filtered = filtered.filter(_.is_show_ask)
elif story_type == "Link Stories Only":
    filtered = filtered.filter(_.is_link)
if author != "All":
    filtered = filtered.filter(_.author == author)

kpi = (
    filtered
    .aggregate(
        "story_count",
        "total_score",
        "avg_score",
        "max_score",
        "total_comments",
        "avg_comments",
        "link_story_count",
        "show_ask_count",
    )
    .to_polars()
    .row(0, named=True)
)

if kpi["story_count"] == 0:
    st.warning("No data found for the selected filters.")
    st.stop()

# 4. Render Dashboard UI
st.title("📈 HackerNews Analytics Dashboard")
st.caption(
    "An analytical dashboard powered by **Boring Semantic Layer** and **DuckDB** / **DuckLake**."
)

st.markdown("---")

# Metrics Row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Stories", f"{kpi['story_count']:,}")
    st.metric("Link Stories", f"{kpi['link_story_count']:,}")

with col2:
    st.metric("Total Score", f"{kpi['total_score']:,}")
    st.metric("Max Score", f"{kpi['max_score']:,}")

with col3:
    st.metric("Total Comments", f"{kpi['total_comments']:,}")
    st.metric("Avg Comments / Story", f"{kpi['avg_comments']:.1f}")

with col4:
    st.metric("Avg Score / Story", f"{kpi['avg_score']:.1f}")
    st.metric("Show / Ask HN Stories", f"{kpi['show_ask_count']:,}")

st.markdown("---")

# Daily Trend Section
st.subheader("📅 Daily Stories & Comments Trends")
daily_trends = (
    filtered
    .group_by("day")
    .aggregate("story_count", "total_comments")
    .order_by("day")
    .to_polars()
)
trend_col1, trend_col2 = st.columns(2)

with trend_col1:
    st.markdown("**Daily Stories Count**")
    st.area_chart(
        daily_trends,
        x="day",
        y="story_count",
        x_label="Date",
        y_label="Story Count",
        color="#6366f1",
        height=300,
    )

with trend_col2:
    st.markdown("**Daily Comments Count**")
    st.area_chart(
        daily_trends,
        x="day",
        y="total_comments",
        x_label="Date",
        y_label="Total Comments",
        color="#10b981",
        height=300,
    )

st.markdown("---")

# Top Items Section
breakdown_col1, breakdown_col2 = st.columns(2)

with breakdown_col1:
    st.subheader(f"🏆 Top {limit_n} Stories by Score")
    st.bar_chart(
        filtered
        .group_by("story_id", "title")
        .aggregate("total_score")
        .order_by(_.total_score.desc())
        .limit(limit_n)
        .to_polars(),
        x="title",
        y="total_score",
        x_label="",
        y_label="Score",
        horizontal=True,
        sort="-total_score",
        color="#6366f1",
        height=350,
    )

with breakdown_col2:
    st.subheader(f"💬 Top {limit_n} Stories by Comments")
    st.bar_chart(
        filtered
        .group_by("story_id", "title")
        .aggregate("total_comments")
        .order_by(_.total_comments.desc())
        .limit(limit_n)
        .to_polars(),
        x="title",
        y="total_comments",
        x_label="",
        y_label="Comments",
        horizontal=True,
        sort="-total_comments",
        color="#10b981",
        height=350,
    )

st.markdown("---")

# Authors Section
st.subheader("👥 Author Analysis")
top_authors = (
    filtered
    .group_by("author")
    .aggregate("story_count", "total_score")
    .order_by(_.story_count.desc())
    .limit(limit_n)
    .to_polars()
)
author_col1, author_col2 = st.columns([2, 1])

with author_col1:
    st.markdown(f"**Top {limit_n} Authors by Story Count**")
    st.bar_chart(
        top_authors,
        x="author",
        y="story_count",
        x_label="Author",
        y_label="Story Count",
        sort="-story_count",
        color="#f59e0b",
        height=350,
    )

with author_col2:
    st.markdown("##### Detailed Author Metrics")
    st.dataframe(
        top_authors,
        column_config={
            "author": "Author",
            "story_count": st.column_config.NumberColumn("Stories", format="%d"),
            "total_score": st.column_config.NumberColumn("Total Score", format="%d"),
        },
        hide_index=True,
        width="stretch",
    )
