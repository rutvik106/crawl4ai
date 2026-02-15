"""Crawl4AI Dashboard — Streamlit app entry point."""

import os
import sys
import base64
from pathlib import Path

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
    page_icon="",
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
    /* Hide the search input in the sidebar */
    .st-emotion-cache-vk33as {
        display: none;
    }
    /* Also hide other potential search containers */
    div[data-testid="stSidebarContent"] > div:nth-child(2) {
        display: none;
    }
    /* Custom navigation styling */
    .nav-item {
        padding: 12px 16px;
        margin-bottom: 4px;
        border-radius: 10px;
        color: #374151;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease-in-out;
        border: 1px solid transparent;
        display: flex;
        align-items: center;
        font-size: 14px;
    }
    .nav-item:hover {
        background-color: #f8fafc;
        color: #1e293b;
        border-color: #e2e8f0;
        transform: translateX(2px);
    }
    .nav-item.active {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        font-weight: 600;
        border-color: #3b82f6;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
    }
    .nav-item.active:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        transform: translateX(0);
    }

</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    # Load and display logo
    logo_path = Path(_project_root) / "New-Logo-Impeerical.jpg"
    if logo_path.exists():
        st.markdown(f"""
        <div style="display: flex; justify-content: center; align-items: center; width: 100%; margin-bottom: 1rem;">
            <div style="background: white; border-radius: 12px; padding: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border: 1px solid #e5e7eb;">
                <img src="data:image/jpeg;base64,{base64.b64encode(open(logo_path, "rb").read()).decode()}" 
                     width="200" style="display: block; margin: 0 auto;">
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('<h1 style="text-align: center;">Impeerical 4 AI</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #6b7280; font-size: 0.875rem;">Smart Web Scraping Dashboard</p>', unsafe_allow_html=True)
    st.divider()
    
    # Custom navigation
    nav_options = ["Dashboard", "New Job", "Jobs", "Schedules", "Settings"]
    
    # Set current page from session state or default
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Dashboard"
    
    for option in nav_options:
        is_active = "active" if st.session_state["current_page"] == option else ""
        
        if st.button(option, key=f"nav_{option}", 
                    help=f"Navigate to {option}",
                    use_container_width=True):
            st.session_state["current_page"] = option
            st.rerun()
        
        # Add custom styling to the button
        active_color = "white" if is_active else "#374151"
        active_weight = "600" if is_active else "500"
        
        st.markdown(f"""
        <script>
            var button = window.parent.document.querySelector('[data-testid="stButton"][data-key="nav_{option}"] button');
            if (button) {{
                button.classList.add('nav-item', '{is_active}');
                button.style.border = 'none';
                button.style.background = 'transparent';
                button.style.color = '{active_color}';
                button.style.padding = '12px 16px';
                button.style.marginBottom = '4px';
                button.style.borderRadius = '10px';
                button.style.fontSize = '14px';
                button.style.fontWeight = '{active_weight}';
                button.style.cursor = 'pointer';
                button.style.transition = 'all 0.2s ease-in-out';
                button.style.textAlign = 'left';
                button.style.justifyContent = 'flex-start';
            }}
        </script>
        """, unsafe_allow_html=True)

# Route to pages
page = st.session_state.get("current_page", "Dashboard")
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
