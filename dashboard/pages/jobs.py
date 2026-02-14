"""Jobs list page — view all jobs, their status, and results."""

import json
import os
import streamlit as st
from dashboard import db


def render():
    st.title("📋 Jobs")

    # Refresh button
    col1, col2 = st.columns([4, 1])
    if col2.button("🔄 Refresh", use_container_width=True):
        st.rerun()

    jobs = db.list_jobs(limit=50)

    if not jobs:
        st.info("No jobs yet. Create one from the **➕ New Job** page.")
        return

    # Filter tabs
    tab_all, tab_running, tab_done, tab_failed = st.tabs(["All", "Running", "Completed", "Failed"])

    with tab_all:
        _render_job_list(jobs, prefix="all")
    with tab_running:
        _render_job_list([j for j in jobs if j["status"] == "running"], prefix="run")
    with tab_done:
        _render_job_list([j for j in jobs if j["status"] == "completed"], prefix="done")
    with tab_failed:
        _render_job_list([j for j in jobs if j["status"] == "failed"], prefix="fail")


def _render_job_list(jobs, prefix=""):
    if not jobs:
        st.caption("No jobs in this category.")
        return

    for idx, job in enumerate(jobs):
        status = job["status"]
        icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "❓")
        uk = f"{prefix}_{idx}_{job['id']}"  # unique key base

        with st.expander(f"{icon} **{job['name']}** — {job['url'][:50]}...", expanded=(status == "running")):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Status", status.upper())
            col2.metric("Articles", job.get("article_count", 0) or 0)
            col3.metric("Created", (job["created_at"] or "")[:16])
            finished = job.get("finished_at") or ""
            col4.metric("Finished", finished[:16] if finished else "—")

            st.caption(f"Job ID: `{job['id']}`")

            if job.get("error"):
                with st.container():
                    st.error("Error Details")
                    st.code(job["error"][:500], language=None)

            # Results section
            output_dir = job.get("output_dir", "")
            if output_dir and os.path.isdir(output_dir):
                st.divider()
                st.subheader("📁 Results")

                # List output files
                files = []
                for root, dirs, fnames in os.walk(output_dir):
                    for f in sorted(fnames):
                        path = os.path.join(root, f)
                        rel = os.path.relpath(path, output_dir)
                        size = os.path.getsize(path)
                        files.append((rel, path, size))

                if files:
                    for rel, path, size in files:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        col1.text(rel)
                        col2.caption(f"{size:,} bytes")

                        if rel.endswith(".json"):
                            if col3.button("View", key=f"{uk}_view_{rel}"):
                                _view_json(path)
                        elif rel.endswith(".png"):
                            if col3.button("View", key=f"{uk}_view_{rel}"):
                                st.image(path, caption=rel, use_container_width=True)
                        elif rel.endswith(".html"):
                            col3.caption("Open in browser")
                        elif rel.endswith(".csv"):
                            if col3.button("View", key=f"{uk}_view_{rel}"):
                                _view_csv(path)

                # Show extracted articles
                json_path = os.path.join(output_dir, "results.json")
                if os.path.exists(json_path):
                    _show_articles(json_path)

            # Actions
            st.divider()
            col1, col2, col3 = st.columns([1, 1, 4])
            if col1.button("🔄 Re-run", key=f"{uk}_rerun"):
                _rerun_job(job)
            if col2.button("🗑️ Delete", key=f"{uk}_del"):
                db.delete_job(job["id"])
                st.rerun()


def _view_json(path):
    try:
        with open(path) as f:
            data = json.load(f)
        st.json(data)
    except Exception as e:
        st.error(f"Error reading JSON: {e}")


def _view_csv(path):
    try:
        import pandas as pd
        df = pd.read_csv(path)
        st.dataframe(df, use_container_width=True)
    except ImportError:
        with open(path) as f:
            st.code(f.read()[:5000], language=None)
    except Exception as e:
        st.error(f"Error reading CSV: {e}")


def _show_articles(json_path):
    try:
        with open(json_path) as f:
            data = json.load(f)

        if not data:
            return

        # Try to get extracted content from the first result
        extracted = None
        if isinstance(data, list) and data:
            ext = data[0].get("extracted", "")
            if isinstance(ext, str) and ext:
                try:
                    extracted = json.loads(ext)
                except json.JSONDecodeError:
                    from crawl4ai.output.email_output import EmailOutput as EO
                    extracted = EO._parse_extracted(ext)
            elif isinstance(ext, list):
                extracted = ext

        if isinstance(extracted, list) and extracted:
            st.subheader(f"📰 Extracted Articles ({len(extracted)})")
            for i, article in enumerate(extracted, 1):
                title = article.get("title", "N/A")
                cat = article.get("category", "")
                source = article.get("source", "")
                summary = article.get("summary", "")

                st.markdown(
                    f"**{i}. {title}**  \n"
                    f"🏷️ `{cat}` · 📰 {source}"
                    + (f"  \n_{summary[:200]}_" if summary else "")
                )

    except Exception:
        pass


def _rerun_job(job):
    from dashboard.engine import run_job_async
    config = json.loads(job["config"]) if isinstance(job["config"], str) else job["config"]
    new_id = __import__("crawl4ai.output.job", fromlist=["generate_job_id"]).generate_job_id()
    db.create_job(job_id=new_id, name=job["name"], url=job["url"], config=config)
    run_job_async(new_id)
    st.success(f"Re-running as job `{new_id}`")
    st.rerun()
