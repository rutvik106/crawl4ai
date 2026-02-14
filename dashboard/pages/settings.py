"""Settings page — API keys, SMTP configuration."""

import os
import streamlit as st
from dashboard import db


def render():
    st.title("⚙️ Settings")
    st.caption("Configure API keys, SMTP credentials, and defaults")

    # Load current settings (fall back to env vars)
    settings = db.get_all_settings()

    st.subheader("🔑 LLM API Keys")

    groq_key = st.text_input(
        "Groq API Key",
        value=settings.get("groq_api_key", os.getenv("GROQ_API_KEY", "")),
        type="password",
    )

    llm_provider = st.selectbox(
        "Default LLM Provider",
        ["groq/llama-3.1-8b-instant", "groq/llama-3.3-70b-versatile", "groq/mixtral-8x7b-32768"],
        index=0,
    )

    st.divider()

    st.subheader("📧 SMTP Configuration")

    col1, col2 = st.columns(2)
    smtp_host = col1.text_input(
        "SMTP Host",
        value=settings.get("smtp_host", os.getenv("SMTP_HOST", "smtp.zoho.in")),
    )
    smtp_port = col2.text_input(
        "SMTP Port",
        value=settings.get("smtp_port", os.getenv("SMTP_PORT", "587")),
    )
    smtp_user = col1.text_input(
        "SMTP User / From Address",
        value=settings.get("smtp_user", os.getenv("SMTP_USER", "")),
    )
    smtp_password = col2.text_input(
        "SMTP Password",
        value=settings.get("smtp_password", os.getenv("SMTP_PASSWORD", "")),
        type="password",
    )

    st.divider()

    st.subheader("🕷️ Crawl Defaults")

    col1, col2 = st.columns(2)
    default_max_scrolls = col1.number_input(
        "Default max scrolls",
        value=int(settings.get("default_max_scrolls", "10")),
        min_value=1,
        max_value=50,
    )
    default_max_inner = col2.number_input(
        "Default max inner pages",
        value=int(settings.get("default_max_inner_pages", "5")),
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
        db.set_setting("llm_provider", llm_provider)
        db.set_setting("smtp_host", smtp_host)
        db.set_setting("smtp_port", smtp_port)
        db.set_setting("smtp_user", smtp_user)
        db.set_setting("smtp_password", smtp_password)
        db.set_setting("default_max_scrolls", str(default_max_scrolls))
        db.set_setting("default_max_inner_pages", str(default_max_inner))
        db.set_setting("default_content_limit", str(default_content_limit))
        st.success("Settings saved!")

    st.divider()

    # Test SMTP connection
    st.subheader("🧪 Test Email")
    test_email = st.text_input("Send test email to", placeholder="your@email.com")
    if st.button("Send Test"):
        if test_email and smtp_host and smtp_user and smtp_password:
            _send_test_email(smtp_host, int(smtp_port), smtp_user, smtp_password, test_email)
        else:
            st.error("Fill in SMTP settings and a test email address first.")


def _send_test_email(host, port, user, password, to):
    import smtplib
    from email.mime.text import MIMEText

    try:
        msg = MIMEText(
            "<h2>Crawl4AI Test Email</h2>"
            "<p>If you see this, your SMTP settings are working correctly! 🎉</p>",
            "html",
        )
        msg["Subject"] = "Crawl4AI: Test Email"
        msg["From"] = user
        msg["To"] = to

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to], msg.as_string())

        st.success(f"Test email sent to {to}!")
    except Exception as e:
        st.error(f"Failed: {e}")
