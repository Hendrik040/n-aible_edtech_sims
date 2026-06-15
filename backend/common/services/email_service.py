"""Outbound email helpers.

Minimal SMTP sender used for transactional emails (currently password resets).

Configuration (environment variables):
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
    SMTP_FROM         - From address (defaults to SMTP_USERNAME)
    SMTP_USE_TLS      - "true"/"false" (default true; STARTTLS)

If SMTP is not configured the service fails closed: it does NOT deliver and, in
non-production environments only, logs the message so developers can complete
the flow locally. The caller must never return the reset token to the client.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True if the minimum SMTP settings are present."""
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_PORT"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send a plaintext email. Returns True if it was handed off to SMTP.

    Fails closed: returns False (and logs) when SMTP is not configured. In
    non-production environments the body is logged to aid local development.
    """
    if not is_configured():
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment in ("production", "prod"):
            logger.error(
                "[EMAIL] SMTP not configured; cannot deliver email to %s (subject=%r). "
                "Set SMTP_HOST/SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD.",
                to_email, subject,
            )
        else:
            # Dev convenience only - never runs in production.
            logger.info("[EMAIL][DEV] To: %s | Subject: %s\n%s", to_email, subject, body)
        return False

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM", username or "no-reply@n-aible.com")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)
        logger.info("[EMAIL] Sent %r to %s", subject, to_email)
        return True
    except Exception as e:  # noqa: BLE001 - log and report failure to caller
        logger.error("[EMAIL] Failed to send email to %s: %s", to_email, e)
        return False


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password-reset email containing the reset link."""
    subject = "Reset your n-aible password"
    body = (
        "We received a request to reset your n-aible password.\n\n"
        f"Use this link to choose a new password (valid for 30 minutes):\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email; your "
        "password will not change."
    )
    return send_email(to_email, subject, body)


__all__ = ["send_email", "send_password_reset_email", "is_configured"]
