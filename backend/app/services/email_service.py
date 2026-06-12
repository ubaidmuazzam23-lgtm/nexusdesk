# File: backend/app/services/email_service.py

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

_SMTP_TIMEOUT = 15

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str) -> bool:
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"NexusDesk <{settings.EMAIL_FROM}>"
        msg['To'] = to
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, to, msg.as_string())
        return True
    except Exception:
        logger.error("Email delivery failed to %s (subject: %s)", to, subject)
        return False


def _base(content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#0f0f0f;border:1px solid rgba(255,255,255,0.07);border-radius:8px;overflow:hidden;">
        <tr><td style="background:#174D38;padding:20px 36px;">
          <span style="font-size:18px;font-weight:700;color:#F2F2F2;letter-spacing:0.03em;">NexusDesk</span>
        </td></tr>
        <tr><td style="padding:36px;">{content}</td></tr>
        <tr><td style="padding:20px 36px;border-top:1px solid rgba(255,255,255,0.06);">
          <p style="margin:0;font-size:11px;color:rgba(242,242,242,0.2);">© 2026 NexusDesk · All rights reserved</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_engineer_credentials_email(to: str, full_name: str, engineer_id: str, temp_password: str) -> bool:
    activate_url = f"{settings.FRONTEND_URL}/auth/activate"
    content = f"""
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:600;color:#F2F2F2;">Your engineer account is ready</h1>
    <p style="margin:0 0 24px;font-size:14px;color:rgba(242,242,242,0.45);line-height:1.7;">
        Hi {full_name}, an admin has created your NexusDesk engineer account.
        Use the credentials below to activate your account — it's a one-time process.
    </p>
    <div style="padding:24px;background:rgba(23,77,56,0.12);border:1px solid rgba(23,77,56,0.35);border-radius:6px;margin-bottom:24px;">
        <p style="margin:0 0 14px;font-size:11px;color:rgba(242,242,242,0.3);letter-spacing:0.1em;text-transform:uppercase;">Your Credentials</p>
        <table cellpadding="0" cellspacing="0" style="width:100%;">
            <tr>
                <td style="font-size:13px;color:rgba(242,242,242,0.4);padding-bottom:10px;width:140px;">Engineer ID</td>
                <td style="font-size:16px;font-weight:700;color:#4d9e78;font-family:monospace;padding-bottom:10px;">{engineer_id}</td>
            </tr>
            <tr>
                <td style="font-size:13px;color:rgba(242,242,242,0.4);padding-bottom:10px;">Email</td>
                <td style="font-size:14px;color:#F2F2F2;padding-bottom:10px;">{to}</td>
            </tr>
            <tr>
                <td style="font-size:13px;color:rgba(242,242,242,0.4);">Temp Password</td>
                <td style="font-size:20px;font-weight:700;color:#4d9e78;font-family:monospace;letter-spacing:0.06em;">{temp_password}</td>
            </tr>
        </table>
    </div>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
        <tr><td style="background:#174D38;border-radius:2px;">
            <a href="{activate_url}" style="display:inline-block;padding:14px 36px;font-size:13px;font-weight:600;color:#F2F2F2;text-decoration:none;letter-spacing:0.06em;text-transform:uppercase;">Activate Account →</a>
        </td></tr>
    </table>
    <p style="margin:0;font-size:12px;color:rgba(242,242,242,0.3);line-height:1.6;">
        After activation you can sign in normally at any time.
    </p>
    """
    return _send(to, f"Activate your NexusDesk engineer account — {engineer_id}", _base(content))


def send_engineer_reactivated_email(to: str, full_name: str, engineer_id: str) -> bool:
    content = f"""
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:600;color:#F2F2F2;">Account Reactivated</h1>
    <p style="margin:0 0 24px;font-size:14px;color:rgba(242,242,242,0.45);line-height:1.7;">
        Hi {full_name}, your NexusDesk engineer account (<strong style="color:#4d9e78;">{engineer_id}</strong>) has been reactivated. You can now sign in.
    </p>
    <table cellpadding="0" cellspacing="0"><tr><td style="background:#174D38;border-radius:2px;">
        <a href="{settings.FRONTEND_URL}/auth/login" style="display:inline-block;padding:13px 32px;font-size:13px;font-weight:600;color:#F2F2F2;text-decoration:none;letter-spacing:0.06em;text-transform:uppercase;">Sign In →</a>
    </td></tr></table>
    """
    return _send(to, f"Your NexusDesk account has been reactivated — {engineer_id}", _base(content))


def send_engineer_deactivated_email(to: str, full_name: str, engineer_id: str) -> bool:
    content = f"""
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:600;color:#F2F2F2;">Account Deactivated</h1>
    <p style="margin:0 0 24px;font-size:14px;color:rgba(242,242,242,0.45);line-height:1.7;">
        Hi {full_name}, your NexusDesk engineer account (<strong style="color:#F2F2F2;">{engineer_id}</strong>) has been deactivated. Contact your admin if you believe this is a mistake.
    </p>
    """
    return _send(to, f"Your NexusDesk account has been deactivated — {engineer_id}", _base(content))


def send_temp_password_email(to: str, full_name: str, temp_password: str) -> bool:
    content = f"""
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:600;color:#F2F2F2;">Your temporary password</h1>
    <p style="margin:0 0 28px;font-size:14px;color:rgba(242,242,242,0.45);line-height:1.7;">Hi {full_name}, here is your temporary password.</p>
    <div style="padding:20px;background:rgba(23,77,56,0.12);border:1px solid rgba(23,77,56,0.35);border-radius:6px;margin-bottom:28px;text-align:center;">
        <p style="margin:0 0 6px;font-size:11px;color:rgba(242,242,242,0.3);letter-spacing:0.1em;text-transform:uppercase;">Temporary Password</p>
        <p style="margin:0;font-size:26px;font-weight:700;color:#4d9e78;letter-spacing:0.08em;font-family:monospace;">{temp_password}</p>
    </div>
    <table cellpadding="0" cellspacing="0"><tr><td style="background:#174D38;border-radius:2px;">
        <a href="{settings.FRONTEND_URL}/auth/login" style="display:inline-block;padding:13px 32px;font-size:13px;font-weight:600;color:#F2F2F2;text-decoration:none;letter-spacing:0.06em;text-transform:uppercase;">Sign In Now →</a>
    </td></tr></table>
    """
    return _send(to, "Your NexusDesk temporary password", _base(content))


def send_welcome_email(to: str, full_name: str) -> bool:
    content = f"""
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:600;color:#F2F2F2;">Welcome to NexusDesk</h1>
    <p style="margin:0 0 24px;font-size:14px;color:rgba(242,242,242,0.45);line-height:1.7;">Hi {full_name}, your account is ready.</p>
    <table cellpadding="0" cellspacing="0"><tr><td style="background:#174D38;border-radius:2px;">
        <a href="{settings.FRONTEND_URL}/chat" style="display:inline-block;padding:13px 32px;font-size:13px;font-weight:600;color:#F2F2F2;text-decoration:none;letter-spacing:0.06em;text-transform:uppercase;">Go to Dashboard →</a>
    </td></tr></table>
    """
    return _send(to, "Welcome to NexusDesk", _base(content))