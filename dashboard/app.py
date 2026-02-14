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
    page_title="Impeerical 4 AI",
    page_icon="�",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for a cleaner look
st.markdown("""
<style>
    /* Hide sidebar navigation menu */
    [data-testid="stSidebarNav"] {
        display: none;
    }
    
    /* Main content styling */
    .stApp {
        background-color: #f8fafc;
    }
    .block-container { 
        padding-top: 3rem; 
        max-width: 1200px;
    }
    
    /* Modern Progress Bar */
    div[data-testid="stProgress"] > div > div > div > div {
        background-image: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%);
        height: 8px;
        border-radius: 10px;
    }
    div[data-testid="stProgress"] {
        background-color: #e2e8f0;
        border-radius: 10px;
        height: 8px;
    }

    /* Card styling */
    .stMetric { 
        background: white; 
        border-radius: 12px; 
        padding: 20px; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
    }
    
    .job-card {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        background: white;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .job-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    div[data-testid="stRadio"] > label {
        display: none;
    }
    div[data-testid="stRadio"] > div {
        background-color: transparent;
        border: none;
        padding: 0;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] {
        gap: 0.5rem;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label {
        background-color: transparent;
        border-radius: 8px;
        padding: 12px 16px;
        border: 1px solid transparent;
        transition: all 0.2s ease;
        cursor: pointer;
        width: 100%;
        margin-bottom: 4px;
        color: #4b5563;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background-color: #f3f4f6;
        color: #111827;
    }
    /* Targeted active state styling for Streamlit's radio labels */
    div[data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked),
    div[data-testid="stRadio"] div[role="radiogroup"] > label[data-checked="true"] {
        background-color: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #2563eb;
        font-weight: 600;
    }
    
    /* Hide the radio circle and focus ring */
    div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
        display: none;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label div[data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        margin: 0;
        line-height: 1.5;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label div[data-testid="stMarkdownContainer"] {
        display: flex;
        align-items: center;
    }
    
    /* Primary Button styling */
    button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        border: none !important;
        padding: 0.5rem 2rem !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
        transform: translateY(-1px);
    }
    
    .status-running { color: #f59e0b; font-weight: bold; }
    .status-completed { color: #10b981; font-weight: bold; }
    .status-failed { color: #ef4444; font-weight: bold; }
    .status-pending { color: #6b7280; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("/Users/rutvikmehta/PycharmProjects/crawl4ai/New-Logo-Impeerical.jpg", use_container_width=True)
    st.markdown("""
        <div style='text-align: center; padding: 0.5rem 0; margin-bottom: 2rem;'>
            <h1 style='margin: 0; font-size: 1.5rem; color: #1e293b; font-weight: 800;'>Impeerical 4 AI</h1>
            <p style='color: #64748b; font-size: 0.85rem; margin: 0; font-weight: 500;'>Advanced Data Intelligence</p>
        </div>
    """, unsafe_allow_html=True)
    
    nav_options = ["Dashboard", "New Job", "Jobs", "Schedules", "Settings"]
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
if page == "Dashboard":
    from pages import dashboard
    dashboard.render()
elif page == "New Job":
    from pages import create_job
    create_job.render()
elif page == "Jobs":
    from pages import jobs
    jobs.render()
elif page == "Schedules":
    from pages import schedules
    schedules.render()
elif page == "Settings":
    from pages import settings
    settings.render()
