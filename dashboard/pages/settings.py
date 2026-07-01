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

    st.subheader("�️ Unblocker Proxy")
    st.caption("BrightData Web Unlocker (or any authenticated proxy). Used for jobs "
               "with 'Use unblocker proxy' enabled, for sites that block direct access.")
    proxy_server = st.text_input(
        "Proxy Server",
        value=settings.get("proxy_server", os.getenv("PROXY_SERVER", "")),
        placeholder="http://brd.superproxy.io:33335",
    )
    pcol1, pcol2 = st.columns(2)
    proxy_username = pcol1.text_input(
        "Proxy Username",
        value=settings.get("proxy_username", os.getenv("PROXY_USERNAME", "")),
    )
    proxy_password = pcol2.text_input(
        "Proxy Password",
        value=settings.get("proxy_password", os.getenv("PROXY_PASSWORD", "")),
        type="password",
    )

    st.divider()

    st.subheader("�🕷️ Crawl Defaults")

    col1, col2 = st.columns(2)
    default_max_scrolls = col1.number_input(
        "Default max scrolls",
        value=int(settings.get("default_max_scrolls", "10")),
        min_value=1,
        max_value=50,
    )
    default_max_inner = col2.number_input(
        "Default max inner pages",
        value=int(settings.get("default_max_inner_pages", "20")),
        min_value=1,
        max_value=50,
    )
    default_content_limit = col1.number_input(
        "Default content limit (chars)",
        value=int(settings.get("default_content_limit", "12000")),
        min_value=1000,
        max_value=100000,
        step=1000,
    )

    st.divider()

    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        db.set_setting("groq_api_key", groq_key)
        db.set_setting("anthropic_api_key", anthropic_key)
        db.set_setting("llm_provider", llm_provider)
        db.set_setting("proxy_server", proxy_server)
        db.set_setting("proxy_username", proxy_username)
        db.set_setting("proxy_password", proxy_password)
        db.set_setting("default_max_scrolls", str(default_max_scrolls))
        db.set_setting("default_max_inner_pages", str(default_max_inner))
        db.set_setting("default_content_limit", str(default_content_limit))
        st.success("Settings saved!")

    st.divider()

    # Test email delivery
    st.subheader("🧪 Test Email")
    st.caption("Sends a test email via the email API to verify delivery is working.")
    test_email = st.text_input("Send test email to", placeholder="your@email.com")
    if st.button("Send Test"):
        if test_email:
            _send_test_email(test_email)
        else:
            st.error("Enter a recipient email address first.")


def _send_test_email(to: str) -> None:
    payload = {
        "to": to,
        "subject": "Test Email",
        "html": "<h2>Crawl4AI Test Email</h2><p>If you see this, your email delivery is working correctly!</p>",
        "text": "Crawl4AI Test Email - If you see this, your email delivery is working correctly!",
    }

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
                st.error(f"Email API returned status {response.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        st.error(f"Failed: HTTP {e.code}: {body}")
    except Exception as e:
        st.error(f"Failed: {e}")
