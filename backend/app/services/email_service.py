import logging
import os
import smtplib

from email.message import EmailMessage


logger = logging.getLogger("ichnos.email")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "Ichnos <no-reply@ichnos.local>")


def send_email(to: str, subject: str, body: str) -> None:
    """
    Sends a plain-text email if SMTP_HOST is configured in the
    environment. If it isn't, logs the email (including any link it
    contains) at INFO level instead of raising - this is what makes
    magic-link login work out of the box on a fresh laptop install
    with zero mail setup: the link shows up in the backend's own logs,
    which is fine for you testing solo, and is exactly the signal that
    real SMTP needs to be configured (see .env.example) before this
    instance is opened up to anyone else.
    """

    if not SMTP_HOST:
        logger.info(
            "EMAIL not sent (SMTP_HOST not configured) - logging instead.\n"
            "To: %s\nSubject: %s\n\n%s",
            to, subject, body,
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = to
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        if SMTP_USERNAME and SMTP_PASSWORD:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)
