"""Outbound email helpers — async SMTP delivery with inline templates."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib

from common.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(
    recipient_email: str,
    subject: str,
    html_body: str,
    plain_body: Optional[str] = None,
) -> bool:
    """Send an email via SMTP.

    Returns True on success, False on failure (never raises — callers should
    not crash because an email failed to send).
    """
    settings = get_settings()

    if not settings.smtp_host or not settings.email_from_address:
        logger.warning(
            "Email sending skipped: SMTP_SERVER / EMAIL_FROM_ADDRESS not configured."
        )
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
    message["To"] = recipient_email

    if plain_body:
        message.attach(MIMEText(plain_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=True,
        )
        logger.info("Email sent to %s — subject: %s", recipient_email, subject)
        return True
    except Exception as exc:
        logger.error(
            "Failed to send email to %s: %s", recipient_email, exc, exc_info=True
        )
        return False


async def send_password_reset_email(
    recipient_email: str,
    user_name: str,
    reset_url: str,
) -> bool:
    """Send a password reset email with an inline HTML template."""
    subject = "Reset your n-aible password"

    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f0f;color:#ffffff;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f0f;padding:40px 20px;">
        <tr>
          <td align="center">
            <table width="100%" style="max-width:520px;background:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;overflow:hidden;">
              <tr>
                <td style="padding:32px 40px;border-bottom:1px solid #2a2a2a;">
                  <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;">n-aible</p>
                </td>
              </tr>
              <tr>
                <td style="padding:40px;">
                  <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#ffffff;">Reset your password</h1>
                  <p style="margin:0 0 24px;font-size:15px;color:#9ca3af;">Hi {user_name},</p>
                  <p style="margin:0 0 32px;font-size:15px;color:#9ca3af;line-height:1.6;">
                    We received a request to reset the password for your n-aible account.
                    Click the button below to choose a new password. This link expires in
                    <strong style="color:#ffffff;">15 minutes</strong>.
                  </p>
                  <a href="{reset_url}"
                     style="display:inline-block;padding:14px 28px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">
                    Reset password
                  </a>
                  <p style="margin:32px 0 0;font-size:13px;color:#6b7280;line-height:1.6;">
                    If you didn't request this, you can safely ignore this email — your
                    password won't change.<br><br>
                    Or copy this link into your browser:<br>
                    <span style="color:#9ca3af;word-break:break-all;">{reset_url}</span>
                  </p>
                </td>
              </tr>
              <tr>
                <td style="padding:24px 40px;border-top:1px solid #2a2a2a;">
                  <p style="margin:0;font-size:12px;color:#6b7280;">© n-aible — AI-powered education platform</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    plain_body = (
        f"Hi {user_name},\n\n"
        "We received a request to reset your n-aible password.\n\n"
        f"Reset your password here (expires in 15 minutes):\n{reset_url}\n\n"
        "If you didn't request this, you can ignore this email."
    )

    return await send_email(recipient_email, subject, html_body, plain_body)
