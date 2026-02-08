"""Crawl4AI Dashboard — Streamlit app entry point."""

import os
import sys

# Ensure project root is on the path so both 'dashboard' and 'crawl4ai' are importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
from dashboard.scheduler import get_scheduler

# Start background scheduler (singleton, only starts once)
get_scheduler()

st.set_page_config(
    page_title="Crawl4AI Dashboard",
    page_icon="🕷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a cleaner look
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .stMetric { background: #f8f9fa; border-radius: 8px; padding: 12px; }
    div[data-testid="stSidebarContent"] { padding-top: 1rem; }
    .job-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        background: white;
    }
    .status-running { color: #f59e0b; font-weight: bold; }
    .status-completed { color: #10b981; font-weight: bold; }
    .status-failed { color: #ef4444; font-weight: bold; }
    .status-pending { color: #6b7280; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("🕷️ Crawl4AI")
    st.caption("Smart Web Scraping Dashboard")
    st.divider()

    nav_options = ["🏠 Dashboard", "➕ New Job", "📋 Jobs", "⏰ Schedules", "⚙️ Settings"]
    default_idx = 0
    if "nav_page" in st.session_state and st.session_state["nav_page"] in nav_options:
        default_idx = nav_options.index(st.session_state["nav_page"])
        del st.session_state["nav_page"]
    page = st.radio(
        "Navigation",
        nav_options,
        index=default_idx,
        label_visibility="collapsed",
    )

# Route to pages
if page == "🏠 Dashboard":
    from pages import dashboard
    dashboard.render()
elif page == "➕ New Job":
    from pages import create_job
    create_job.render()
elif page == "📋 Jobs":
    from pages import jobs
    jobs.render()
elif page == "⏰ Schedules":
    from pages import schedules
    schedules.render()
elif page == "⚙️ Settings":
    from pages import settings
    settings.render()
