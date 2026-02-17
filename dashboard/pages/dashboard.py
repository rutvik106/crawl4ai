"""Dashboard home page — overview stats and recent jobs."""

import streamlit as st
from dashboard import db
from datetime import datetime


def format_date(date_val):
    """Format date to human readable format."""
    if not date_val:
        return ""
    try:
        # Handle datetime object directly (PostgreSQL)
        if isinstance(date_val, datetime):
            return date_val.strftime("%b %d, %Y, %I:%M %p")
        # Handle string format (SQLite fallback)
        dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
        return dt.strftime("%b %d, %Y, %I:%M %p")
    except Exception:
        return str(date_val)[:16]


def render():
    st.title("Dashboard")
    st.caption("Overview of your crawl jobs")

    jobs = db.list_jobs(limit=100)

    # Schedules summary
    scheds = db.list_schedules()
    active_scheds = sum(1 for s in scheds if s.get("enabled"))

    # Stats row
    total = len(jobs)
    running = sum(1 for j in jobs if j["status"] == "running")
    completed = sum(1 for j in jobs if j["status"] == "completed")
    failed = sum(1 for j in jobs if j["status"] == "failed")
    total_articles = sum(j.get("article_count", 0) or 0 for j in jobs)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Total Jobs", total)
    col2.metric("Running", running)
    col3.metric("Completed", completed)
    col4.metric("Failed", failed)
    col5.metric("Articles Extracted", total_articles)
    col6.metric("Active Schedules", active_scheds)

    st.divider()

    # Recent jobs
    st.subheader("Recent Jobs")

    if not jobs:
        st.info("No jobs yet. Create one from the **➕ New Job** page.")
        return

    for job in jobs[:10]:
        status = job["status"]
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }.get(status, "❓")

        with st.container():
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.markdown(f"**{status_icon} {job['name']}**")
            c2.caption(job["url"][:60])
            c3.caption(f"{job.get('article_count', 0) or 0} articles")
            c4.caption(format_date(job["created_at"]))
