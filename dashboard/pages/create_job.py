"""Job creation wizard — step-by-step crawl job setup."""

import json
import streamlit as st
from dashboard import db
from dashboard.engine import run_job_async
from crawl4ai.output.job import generate_job_id


def render():
    st.title("Create New Job")

    # Wizard steps
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 1

    step = st.session_state.wizard_step

    # Progress bar
    st.progress(step / 5, text=f"Step {step} of 5")

    if step == 1:
        _step_source()
    elif step == 2:
        _step_schema()
    elif step == 3:
        _step_navigation()
    elif step == 4:
        _step_recipients()
    elif step == 5:
        _step_review()


def _step_source():
    st.subheader("1. Source URL")
    st.caption("Enter the website URL you want to crawl")

    url = st.text_input(
        "URL",
        value=st.session_state.get("job_url", ""),
        placeholder="https://example.comnews",
    )
    name = st.text_input(
        "Job Name",
        value=st.session_state.get("job_name", ""),
        placeholder="Pharma News Feed",
    )

    col1, col2 = st.columns([4, 1])
    if col2.button("Next →", use_container_width=True, type="primary"):
        if not url:
            st.error("Please enter a URL")
            return
        if not name:
            name = url.split("//")[-1].split("/")[0]
        st.session_state.job_url = url
        st.session_state.job_name = name
        st.session_state.wizard_step = 2
        st.rerun()


def _step_schema():
    st.subheader("2. What to Extract")
    st.caption("Define the fields you want to extract from each article")

    mode = st.radio(
        "Schema mode",
        ["AI Auto-detect (recommended)", "Define manually", "Use preset: News Articles"],
        index=2,
    )

    if mode == "Use preset: News Articles":
        st.session_state.job_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The news headline"},
                "source": {"type": "string", "description": "Publisher name"},
                "category": {"type": "string", "description": "Category (e.g. pharma, business, tech)"},
                "summary": {"type": "string", "description": "One-sentence summary"},
            },
            "required": ["title"],
        }
        st.json(st.session_state.job_schema)

    elif mode == "AI Auto-detect (recommended)":
        st.session_state.job_schema = {}
        st.info("AI will analyze the page and auto-suggest fields during crawl.")

    elif mode == "Define manually":
        fields_json = st.text_area(
            "Schema JSON",
            value=json.dumps(st.session_state.get("job_schema", {}), indent=2),
            height=200,
        )
        try:
            st.session_state.job_schema = json.loads(fields_json) if fields_json.strip() else {}
        except json.JSONDecodeError:
            st.error("Invalid JSON")

    custom_instruction = st.text_area(
        "Custom extraction instruction (optional)",
        value=st.session_state.get("job_instruction", ""),
        placeholder="Extract only pharma industry news articles. Ignore promotional content...",
    )
    st.session_state.job_instruction = custom_instruction

    col1, col2, col3 = st.columns([1, 3, 1])
    if col1.button("← Back", use_container_width=True):
        st.session_state.wizard_step = 1
        st.rerun()
    if col3.button("Next →", use_container_width=True, type="primary"):
        st.session_state.wizard_step = 3
        st.rerun()


def _step_navigation():
    st.subheader("3. How to Navigate")
    st.caption("Configure how the crawler explores the page")

    nav_mode = st.radio(
        "Navigation strategy",
        [
            "Single page — stay on this page, extract data",
            "List (scroll + pagination) — auto-scroll and paginate",
            "List + Details — follow links to inner article pages",
        ],
        index=2,
    )

    config = st.session_state.get("job_nav_config", {})

    if "List" in nav_mode:
        col1, col2 = st.columns(2)
        config["scroll"] = col1.checkbox("Auto-scroll page", value=config.get("scroll", True))
        config["max_scrolls"] = col2.number_input("Max scrolls", 1, 50, config.get("max_scrolls", 10))
        config["click_load_more"] = col1.checkbox("Click 'Load More' buttons", value=config.get("click_load_more", True))

    if "Details" in nav_mode:
        config["follow_links"] = True
        col1, col2 = st.columns(2)
        config["max_inner_pages"] = col1.number_input("Max inner pages", 1, 50, config.get("max_inner_pages", 5))
        config["link_filter"] = col2.text_input(
            "Link URL filter (regex)",
            value=config.get("link_filter", ""),
            placeholder=r"/news/.*\d",
        )
    else:
        config["follow_links"] = False

    col1, col2 = st.columns(2)
    config["smart_filter"] = col1.checkbox("Smart noise filter (AI)", value=config.get("smart_filter", True))
    config["screenshots"] = col2.checkbox("Take screenshots", value=config.get("screenshots", True))

    st.session_state.job_nav_config = config

    col1, col2, col3 = st.columns([1, 3, 1])
    if col1.button("← Back", use_container_width=True):
        st.session_state.wizard_step = 2
        st.rerun()
    if col3.button("Next →", use_container_width=True, type="primary"):
        st.session_state.wizard_step = 4
        st.rerun()


def _step_recipients():
    st.subheader("4. Email Recipients & Schedule")

    recipients = st.text_input(
        "Email recipients (comma-separated)",
        value=st.session_state.get("job_recipients", ""),
        placeholder="alice@company.com, bob@company.com",
    )
    st.session_state.job_recipients = recipients

    email_subject = st.text_input(
        "Email subject (optional)",
        value=st.session_state.get("job_email_subject", ""),
        placeholder=f"Crawl4AI: {st.session_state.get('job_name', 'News Feed')}",
    )
    st.session_state.job_email_subject = email_subject

    st.divider()

    run_mode = st.radio(
        "When to run",
        ["Run once (now)", "Schedule recurring"],
        index=0,
    )
    st.session_state.job_run_mode = run_mode

    if run_mode == "Schedule recurring":
        sched_type = st.radio(
            "Schedule type",
            ["Every X hours / minutes", "Specific days & time"],
            horizontal=True,
        )

        if sched_type == "Every X hours / minutes":
            col1, col2 = st.columns(2)
            interval_options = [
                "Every 5 minutes",
                "Every 30 minutes",
                "Every 1 hour",
                "Every 2 hours",
                "Every 4 hours",
                "Every 6 hours",
                "Every 8 hours",
                "Every 12 hours",
            ]
            interval = col1.selectbox("Interval", interval_options, index=1)
            interval_cron = {
                "Every 5 minutes": "*/5 * * * *",
                "Every 30 minutes": "*/30 * * * *",
                "Every 1 hour": "0 * * * *",
                "Every 2 hours": "0 */2 * * *",
                "Every 4 hours": "0 */4 * * *",
                "Every 6 hours": "0 */6 * * *",
                "Every 8 hours": "0 */8 * * *",
                "Every 12 hours": "0 */12 * * *",
            }
            cron = interval_cron[interval]
            col2.code(f"Cron: {cron}", language=None)

        else:
            # Day selector
            all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            selected_days = st.multiselect(
                "Run on days",
                all_days,
                default=st.session_state.get("job_sched_days", all_days),
            )
            st.session_state.job_sched_days = selected_days

            # Time selector with 30-min intervals
            time_slots = []
            for h in range(24):
                for m in (0, 30):
                    hour_12 = h % 12 or 12
                    ampm = "AM" if h < 12 else "PM"
                    time_slots.append(f"{hour_12}:{m:02d} {ampm}")

            selected_time = st.selectbox(
                "Run at time",
                time_slots,
                index=time_slots.index(st.session_state.get("job_sched_time", "9:00 AM")),
            )
            st.session_state.job_sched_time = selected_time

            # Convert to cron
            day_map = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6, "Sunday": 0}
            if selected_days and len(selected_days) == 7:
                cron_days = "*"
            elif selected_days:
                cron_days = ",".join(str(day_map[d]) for d in selected_days)
            else:
                cron_days = "*"

            # Parse time
            import re as _re
            _m = _re.match(r"(\d+):(\d+)\s*(AM|PM)", selected_time)
            if _m:
                hr = int(_m.group(1))
                mn = int(_m.group(2))
                ap = _m.group(3)
                if ap == "PM" and hr != 12:
                    hr += 12
                elif ap == "AM" and hr == 12:
                    hr = 0
            else:
                hr, mn = 9, 0

            cron = f"{mn} {hr} * * {cron_days}"
            st.code(f"Cron: {cron}", language=None)

        st.session_state.job_cron = cron

    col1, col2, col3 = st.columns([1, 3, 1])
    if col1.button("← Back", use_container_width=True):
        st.session_state.wizard_step = 3
        st.rerun()
    if col3.button("Next →", use_container_width=True, type="primary"):
        st.session_state.wizard_step = 5
        st.rerun()


def _step_review():
    st.subheader("5. Review & Create")

    name = st.session_state.get("job_name", "Untitled")
    url = st.session_state.get("job_url", "")
    nav = st.session_state.get("job_nav_config", {})
    recipients = st.session_state.get("job_recipients", "")
    run_mode = st.session_state.get("job_run_mode", "Run once (now)")

    # Summary card
    st.markdown(f"### {name}")
    col1, col2 = st.columns(2)
    col1.markdown(f"**Source:** `{url}`")
    col2.markdown(f"**Recipients:** {recipients or 'None'}")

    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Scroll:** {'Yes' if nav.get('scroll') else 'No'} ({nav.get('max_scrolls', 0)} max)")
    col2.markdown(f"**Follow links:** {'Yes' if nav.get('follow_links') else 'No'} ({nav.get('max_inner_pages', 0)} pages)")
    col3.markdown(f"**Smart filter:** {'Yes' if nav.get('smart_filter') else 'No'}")

    st.markdown(f"**Run mode:** {run_mode}")
    if run_mode == "Schedule recurring":
        st.markdown(f"**Cron:** `{st.session_state.get('job_cron', '')}`")

    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])

    if col1.button("← Back", use_container_width=True):
        st.session_state.wizard_step = 4
        st.rerun()

    if col3.button("🚀 Create & Run", use_container_width=True, type="primary"):
        _create_and_run()


def _create_and_run():
    job_id = generate_job_id()
    name = st.session_state.get("job_name", "Untitled")
    url = st.session_state.get("job_url", "")
    nav = st.session_state.get("job_nav_config", {})

    config = {
        **nav,
        "schema_fields": st.session_state.get("job_schema", {}),
        "extraction_instruction": st.session_state.get("job_instruction", ""),
        "recipients": st.session_state.get("job_recipients", ""),
        "email_subject": st.session_state.get("job_email_subject", ""),
    }

    # Create job record
    db.create_job(job_id=job_id, name=name, url=url, config=config)

    # If scheduled, create schedule too
    run_mode = st.session_state.get("job_run_mode", "Run once (now)")
    if run_mode == "Schedule recurring":
        db.create_schedule(
            job_name=name,
            url=url,
            config=config,
            cron=st.session_state.get("job_cron", "0 9 * * *"),
            recipients=config.get("recipients", ""),
        )

    # Launch job in background
    run_job_async(job_id)

    # Reset wizard
    for key in list(st.session_state.keys()):
        if key.startswith("job_") or key == "wizard_step":
            del st.session_state[key]

    # Navigate to Jobs page
    st.session_state["nav_page"] = "📋 Jobs"
    st.rerun()
