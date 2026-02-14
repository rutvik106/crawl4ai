"""Dashboard home page — overview stats and recent jobs."""

import streamlit as st
from dashboard import db


def render():
    st.title("Dashboard")
    st.caption("Overview of your intelligence jobs")

    jobs = db.list_jobs(limit=100)

    # Stats row
    total = len(jobs)
    running = sum(1 for j in jobs if j["status"] == "running")
    completed = sum(1 for j in jobs if j["status"] == "completed")
    failed = sum(1 for j in jobs if j["status"] == "failed")
    total_articles = sum(j.get("article_count", 0) or 0 for j in jobs)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Jobs", total)
    col2.metric("Running", running)
    col3.metric("Completed", completed)
    col4.metric("Failed", failed)
    col5.metric("Articles Extracted", total_articles)

    st.divider()

    # Schedules summary
    scheds = db.list_schedules()
    active_scheds = sum(1 for s in scheds if s.get("enabled"))
    st.subheader(f"Active Schedules: {active_scheds}")

    st.divider()

    # Recent jobs
    st.subheader("Recent Jobs")

    if not jobs:
        st.info("No jobs yet. Create one from the **➕ New Job** page.")
        return

    for job in jobs[:10]:
        status = job["status"]
        status_text = {
            "pending": "Pending",
            "running": "Running",
            "completed": "Completed",
            "failed": "Failed",
        }.get(status, "Unknown")

        with st.container():
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.markdown(f"**{job['name']}**")
            c2.caption(job["url"][:60])
            c3.caption(f"{job.get('article_count', 0) or 0} articles")
            c4.caption(job["created_at"][:16] if job["created_at"] else "")
