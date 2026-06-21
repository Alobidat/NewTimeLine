"""Email sender behind an interface — used for verification mail (ADR-0026).

Two implementations: :class:`SmtpSender` (real, stdlib ``smtplib``) and :class:`ConsoleSender`
(no-op log; for dev/tests). :func:`get_sender` picks SMTP when ``smtp_host`` is configured,
else the console stub — so tests and a fresh dev box never need a live SMTP server.

We also keep verification *codes* here: a code is a short signed-JWT (HS256) carrying the
email + purpose + expiry, so confirm is a pure verify with no extra storage table. The same
``jwt_secret`` signs them; they are independent of session tokens via the ``purpose`` claim.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Protocol

from chronos_core.auth import jwt
from chronos_core.settings import get_settings

log = logging.getLogger("chronos.auth.email")

VERIFY_TTL_SECONDS = 60 * 30  # an emailed verification link/code is valid 30 minutes


class EmailSender(Protocol):
    """Send a plain-text email. Implementations must not raise on transient failure paths
    that the caller can't recover from — log and swallow, or raise a clear error."""

    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleSender:
    """Dev/test sender: logs the message instead of delivering it."""

    def send(self, to: str, subject: str, body: str) -> None:
        log.info("EMAIL (console) to=%s subject=%s\n%s", to, subject, body)


class SmtpSender:
    """Real SMTP sender over stdlib ``smtplib`` (STARTTLS optional)."""

    def __init__(self, settings) -> None:  # noqa: ANN001 - Settings, avoid import cycle
        self._s = settings

    def send(self, to: str, subject: str, body: str) -> None:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(self._s.smtp_host, self._s.smtp_port) as smtp:
            if self._s.smtp_starttls:
                smtp.starttls()
            if self._s.smtp_user:
                smtp.login(self._s.smtp_user, self._s.smtp_password)
            smtp.send_message(msg)


def get_sender() -> EmailSender:
    """SMTP sender when configured, else the console stub."""
    settings = get_settings()
    return SmtpSender(settings) if settings.smtp_host else ConsoleSender()


def make_code(email: str) -> str:
    """Issue a short-lived signed verification code bound to an email address."""
    now = int(time.time())
    payload = {
        "email": email.lower(),
        "purpose": "email_verify",
        "nonce": secrets.token_hex(8),
        "iat": now,
        "exp": now + VERIFY_TTL_SECONDS,
    }
    return jwt.encode(payload, get_settings().jwt_secret)


def check_code(code: str, email: str) -> bool:
    """True iff ``code`` is a valid, unexpired verification code for ``email``."""
    try:
        claims = jwt.decode(code, get_settings().jwt_secret)
    except jwt.JWTError:
        return False
    return (
        claims.get("purpose") == "email_verify"
        and claims.get("email") == email.lower()
    )
