"""Schedules page — manage recurring jobs."""

import json
import streamlit as st
from dashboard import db


def render():
    st.title("Schedules")
    st.caption("Manage recurring jobs")

    schedules = db.list_schedules()

    if not schedules:
        st.info("No schedules yet. Create one from the **➕ New Job** page by selecting 'Schedule recurring'.")
        return

    for sched in schedules:
        enabled = bool(sched.get("enabled", 1))
        icon = "🟢" if enabled else "🔴"

        with st.expander(f"{icon} **{sched['job_name']}** — `{sched['cron']}`", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"**URL:** {sched['url'][:60]}")
            col2.markdown(f"**Cron:** `{sched['cron']}`")
            col3.markdown(f"**Recipients:** {sched.get('recipients', 'None')}")

            col1, col2 = st.columns(2)
            last = sched.get("last_run") or "Never"
            nxt = sched.get("next_run") or "—"
            col1.markdown(f"**Last run:** {last}")
            col2.markdown(f"**Next run:** {nxt}")

            st.divider()
            col1, col2, col3, col4 = st.columns([1, 1, 1, 3])

            if enabled:
                if col1.button("⏸️ Disable", key=f"dis_{sched['id']}"):
                    db.update_schedule(sched["id"], enabled=0)
                    st.rerun()
            else:
                if col1.button("▶️ Enable", key=f"en_{sched['id']}"):
                    db.update_schedule(sched["id"], enabled=1)
                    st.rerun()

            if col2.button("▶ Run Now", key=f"run_{sched['id']}"):
                _run_schedule_now(sched)

            if col3.button("🗑️ Delete", key=f"del_{sched['id']}"):
                db.delete_schedule(sched["id"])
                st.rerun()


def _run_schedule_now(sched):
    """Trigger an immediate run of a scheduled job."""
    from dashboard.engine import run_job_async
    from crawl4ai.output.job import generate_job_id

    config = json.loads(sched["config"]) if isinstance(sched["config"], str) else sched["config"]
    job_id = generate_job_id()
    db.create_job(
        job_id=job_id,
        name=f"{sched['job_name']} (manual)",
        url=sched["url"],
        config=config,
    )
    run_job_async(job_id)
    st.success(f"Running now as job `{job_id}`")
