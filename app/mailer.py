"""
Outgoing mail: for now, only the password-reset link.

Two ways out, configured by environment variables:

    CAMPUS_BREVO_API_KEY  Brevo's HTTP API (https://api.brevo.com). Preferred:
                          it goes over HTTPS, which every host allows — free
                          Render, for one, blocks the SMTP ports.
    CAMPUS_SMTP_HOST      an SMTP server, e.g. smtp.gmail.com, used when there
                          is no Brevo key
    CAMPUS_SMTP_PORT      587 by default (STARTTLS); 465 switches to implicit TLS
    CAMPUS_SMTP_USER      login, if the server wants one
    CAMPUS_SMTP_PASSWORD
    CAMPUS_MAIL_FROM      the sender; with Brevo it must be a sender verified
                          in the Brevo account. CAMPUS_SMTP_USER by default.

With neither configured nothing is sent: the link is written to the server log
instead, which is what you want on a laptop and never what you want in
production.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from html import escape

log = logging.getLogger("campus.mail")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
SENDER_NAME = "SDU Campus Assistant"
SUBJECT = "Reset your SDU Campus Assistant password"


def mail_configured() -> bool:
    return bool(os.environ.get("CAMPUS_BREVO_API_KEY") or os.environ.get("CAMPUS_SMTP_HOST"))


def _sender() -> str:
    return os.environ.get("CAMPUS_MAIL_FROM") or os.environ.get("CAMPUS_SMTP_USER", "")


def _texts(link: str, minutes: int) -> tuple[str, str]:
    text = (
        "Someone — hopefully you — asked to reset the password of your SDU Campus "
        "Assistant account.\n\n"
        f"Choose a new password here (the link works once, for {minutes} minutes):\n\n"
        f"{link}\n\n"
        "If it wasn't you, ignore this email: your password stays as it is.\n"
    )
    html = (
        "<p>Someone — hopefully you — asked to reset the password of your SDU Campus "
        "Assistant account.</p>"
        f'<p><a href="{escape(link)}">Choose a new password</a> — the link works once, '
        f"for {minutes} minutes.</p>"
        f'<p style="color:#555">If the button does not open, copy this address:<br>{escape(link)}</p>'
        "<p>If it wasn't you, ignore this email: your password stays as it is.</p>"
    )
    return text, html


def send_reset_link(email: str, link: str, minutes: int) -> bool:
    """Mail the link. True when the mail service accepted it; a failure is
    logged, because the person has already been answered."""
    if os.environ.get("CAMPUS_BREVO_API_KEY"):
        return _send_brevo(email, link, minutes)
    if os.environ.get("CAMPUS_SMTP_HOST"):
        return _send_smtp(email, link, minutes)
    log.warning("No mail service configured (CAMPUS_BREVO_API_KEY or CAMPUS_SMTP_HOST) — "
                "password reset link for %s: %s", email, link)
    return False


def _send_brevo(email: str, link: str, minutes: int) -> bool:
    text, html = _texts(link, minutes)
    payload = {
        "sender": {"email": _sender(), "name": SENDER_NAME},
        "to": [{"email": email}],
        "subject": SUBJECT,
        "textContent": text,
        "htmlContent": html,
    }
    request = urllib.request.Request(
        BREVO_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"api-key": os.environ["CAMPUS_BREVO_API_KEY"],
                 "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            log.info("Password reset email to %s accepted by Brevo (%s)", email, response.status)
            return True
    except urllib.error.HTTPError as err:
        # Brevo says why: an unverified sender, a bad key, a blocked account
        log.error("Brevo refused the password reset email to %s: %s %s",
                  email, err.code, err.read().decode(errors="replace")[:500])
    except OSError:
        log.exception("Could not reach Brevo to send the password reset email to %s", email)
    return False


def _send_smtp(email: str, link: str, minutes: int) -> bool:
    text, html = _texts(link, minutes)
    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = _sender()
    msg["To"] = email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    host = os.environ["CAMPUS_SMTP_HOST"]
    port = int(os.environ.get("CAMPUS_SMTP_PORT", "587"))
    user = os.environ.get("CAMPUS_SMTP_USER")
    password = os.environ.get("CAMPUS_SMTP_PASSWORD")
    context = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=context)
        with server:
            if user:
                server.login(user, password or "")
            server.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        # the request has already been answered; all that is left is to say so
        log.exception("Could not send the password reset email to %s", email)
        return False
