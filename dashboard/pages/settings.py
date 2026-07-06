"""Settings page — API keys and crawl defaults."""

import json
import os
import urllib.request
import urllib.error
import streamlit as st
from dashboard import db

EMAIL_API_URL = "https://time-tracker-3-sigma.vercel.app/api/v1/users/emailsend"


def render():
    st.title("Settings")
    st.caption("Configure API keys and crawl defaults")

    # Load current settings (fall back to env vars)
    settings = db.get_all_settings()

    st.subheader("🔑 LLM API Keys")

    groq_key = st.text_input(
        "Groq API Key",
        value=settings.get("groq_api_key", os.getenv("GROQ_API_KEY", "")),
        type="password",
    )

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=settings.get("anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", "")),
        type="password",
    )

    _providers = [
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-3-5-haiku-latest",
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
    ]
    _current = settings.get("llm_provider", "anthropic/claude-sonnet-4-5")
    if _current not in _providers:
        _providers.insert(0, _current)
    llm_provider = st.selectbox(
        "Default LLM Provider",
        _providers,
        index=_providers.index(_current),
    )

    st.divider()

    st.subheader("🛡
            st.error("Enter a recipient email address first.")


def _send_test_email(to: str) -> None:
    payload = {
        "to": to,
        "subject": "Test Email", l</Ia

    req = urllib.request.Request(
        EMAIL_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status in (200, 201, 202):
                st.success(f"Test email sent to {to}!")
            else:
                sterror(f"Email API returned status {response.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        st.error(f"Failed: HTTP {e.code}: {body}")
    except Exception as e:
        st.error(f"Failed: {e}")
