"""Outbound email helpers (SMTP).

Provides async email sending via SMTP with STARTTLS. SMTP calls run in a
thread executor to avoid blocking the asyncio event loop (matching the
pattern used in :mod:`common.security.passwords`).
"""
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from common.config import get_settings

logger = logging.getLogger(__name__)


def _send_email_sync(
    recipient: str,
    subject: str,
    html_body: str,
    *,
    smtp_server: str,
    smtp_port: int,
    smtp_username: Optional[str],
    smtp_password: Optional[str],
    from_email: str,
    from_name: str,
) -> None:
    """Blocking SMTP send — intended to be run inside a thread executor."""
    message = EmailMessage()
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = recipient
    message["Subject"] = subject
    # Provide a plain-text fallback so the message is multipart/alternative.
    message.set_content(
        "This email requires an HTML-capable mail client to view correctly."
    )
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


async def send_email(recipient: str, subject: str, html_body: str) -> bool:
    """Send an HTML email asynchronously.

    Returns True on success, False on failure (failures are logged but not
    raised so callers can respond with generic messages to avoid leaking
    information — e.g. in the password reset flow).
    """
    settings = get_settings()

    # Required configuration check. In local/dev environments SMTP may not
    # be configured; in that case log and return False so callers can decide
    # how to handle it (the password reset flow still returns a generic
    # success message to the client).
    from_email = settings.from_email or settings.smtp_username
    if not from_email:
        logger.warning(
            "send_email: SMTP sender address is not configured "
            "(set FROM_EMAIL or SMTP_USERNAME). Skipping send."
        )
        return False

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: _send_email_sync(
                recipient,
                subject,
                html_body,
                smtp_server=settings.smtp_server,
                smtp_port=settings.smtp_port,
                smtp_username=settings.smtp_username,
                smtp_password=settings.smtp_password,
                from_email=from_email,
                from_name=settings.from_name,
            ),
        )
        logger.info("send_email: delivered to %s (subject=%r)", recipient, subject)
        return True
    except Exception as exc:  # pragma: no cover — network/SMTP errors
        logger.error(
            "send_email: failed to deliver to %s: %s", recipient, exc, exc_info=True
        )
        return False


def _build_password_reset_html(reset_link: str) -> str:
    return f"""<!DOCTYPE html>
<html>
  <body style="font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; padding:24px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px; margin:0 auto; background:#1e293b; border-radius:12px; padding:32px;">
      <tr><td>
        <h1 style="color:#f8fafc; margin-top:0;">Reset your password</h1>
        <p>We received a request to reset the password for your n-aible account.</p>
        <p>Click the button below to choose a new password. This link will expire in 1 hour.</p>
        <p style="text-align:center; margin:32px 0;">
          <a href="{reset_link}" style="display:inline-block; background:#6366f1; color:#ffffff; text-decoration:none; padding:12px 24px; border-radius:8px; font-weight:600;">Reset password</a>
        </p>
        <p style="font-size:13px; color:#94a3b8;">If the button doesn't work, copy and paste this URL into your browser:</p>
        <p style="font-size:13px; word-break:break-all; color:#cbd5e1;">{reset_link}</p>
        <hr style="border:none; border-top:1px solid #334155; margin:24px 0;" />
        <p style="font-size:12px; color:#94a3b8;">If you didn't request this, you can safely ignore this email — your password won't be changed.</p>
      </td></tr>
    </table>
  </body>
</html>
"""


async def send_password_reset_email(email: str, reset_link: str) -> bool:
    """Send the password reset email to the user."""
    subject = "Reset your n-aible password"
    html_body = _build_password_reset_html(reset_link)
    return await send_email(email, subject, html_body)


__all__ = ["send_email", "send_password_reset_email"]
