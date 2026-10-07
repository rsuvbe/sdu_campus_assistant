"""
Outgoing mail: for now, only the password-reset link.

Configured by environment variables:

    CAMPUS_SMTP_HOST      the SMTP server, e.g. smtp.gmail.com — unset means "no mail"
    CAMPUS_SMTP_PORT      587 by default (STARTTLS); 465 switches to implicit TLS
    CAMPUS_SMTP_USER      login, if the server wants one
    CAMPUS_SMTP_PASSWORD
    CAMPUS_MAIL_FROM      the sender, CAMPUS_SMTP_USER by default

Without CAMPUS_SMTP_HOST nothing is sent: the link is written to the server log
instead, which is what you want on a laptop and never what you want in
production.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("campus.mail")


def mail_configured() -> bool:
    return bool(os.environ.get("CAMPUS_SMTP_HOST"))


def send_reset_link(email: str, link: str, minutes: int) -> None:
    body = (
        "Someone — hopefully you — asked to reset the password of your SDU Campus "
        "Assistant account.\n\n"
        f"Choose a new password here (the link works once, for {minutes} minutes):\n\n"
        f"{link}\n\n"
        "If it wasn't you, ignore this email: your password stays as it is.\n"
    )
    if not mail_configured():
        log.warning("No SMTP server configured (CAMPUS_SMTP_HOST) — password reset link "
                    "for %s: %s", email, link)
        return

    msg = EmailMessage()
    msg["Subject"] = "Reset your SDU Campus Assistant password"
    msg["From"] = os.environ.get("CAMPUS_MAIL_FROM") or os.environ.get("CAMPUS_SMTP_USER", "")
    msg["To"] = email
    msg.set_content(body)

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
    except (OSError, smtplib.SMTPException):
        # the request has already been answered; all that is left is to say so
        log.exception("Could not send the password reset email to %s", email)
