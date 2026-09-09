"""Lightweight email sender for operational alerts.

Uses Python's built-in smtplib + email.mime.  Configure via environment:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, ADMIN_EMAIL
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from ..core.config import settings

logger = logging.getLogger(__name__)


def _smtp_credentials() -> dict[str, str] | None:
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    password = settings.SMTP_PASS
    if not all([host, port, user, password]):
        return None
    return {"host": host, "port": int(port), "user": user, "password": password}


def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns True on success, False otherwise."""
    creds = _smtp_credentials()
    if not creds:
        logger.warning("SMTP not configured — email not sent to %s", to)
        return False

    smtp_from = settings.SMTP_FROM or creds["user"]
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(creds["host"], creds["port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(creds["user"], creds["password"])
            server.sendmail(smtp_from, [to], msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


def send_low_balance_alert(
    service_type: str,
    amount_naira: float,
    user_email: str,
    provider_balance_naira: float,
) -> bool:
    """Notify the admin when a purchase fails due to low provider balance."""
    admin_email = settings.ADMIN_EMAIL
    if not admin_email:
        logger.warning("ADMIN_EMAIL not set — cannot send low-balance alert")
        return False

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"Low Provider Balance — {settings.APP_NAME}"
    html = f"""
    <div style="font-family:system-ui,-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
      <div style="background:#feeceb;border-left:4px solid #dc3545;padding:16px;border-radius:6px;margin-bottom:20px;">
        <h2 style="margin:0;color:#dc3545;font-size:18px;">Insufficient Provider Balance</h2>
      </div>
      <p style="font-size:15px;color:#333;">A user attempted to purchase a service but your reseller wallet balance is too low.</p>
      <table style="width:100%;border-collapse:collapse;margin:20px 0;">
        <tr><td style="padding:8px 0;color:#666;font-weight:600;">Service</td><td style="padding:8px 0;">{service_type}</td></tr>
        <tr><td style="padding:8px 0;color:#666;font-weight:600;">Amount</td><td style="padding:8px 0;">₦{amount_naira:,.2f}</td></tr>
        <tr><td style="padding:8px 0;color:#666;font-weight:600;">User</td><td style="padding:8px 0;">{user_email}</td></tr>
        <tr><td style="padding:8px 0;color:#dc3545;font-weight:600;">Provider Balance</td><td style="padding:8px 0;color:#dc3545;font-weight:600;">₦{provider_balance_naira:,.2f}</td></tr>
        <tr><td style="padding:8px 0;color:#666;font-weight:600;">Time</td><td style="padding:8px 0;">{now}</td></tr>
      </table>
      <p style="font-size:14px;color:#666;">Please top up your reseller wallet immediately to avoid service interruption.</p>
    </div>
    """
    return send_email(admin_email, subject, html)
