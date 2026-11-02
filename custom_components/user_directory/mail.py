"""Send email through the admin's SMTP server."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.ssl import client_context

from .const import (
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SECURITY,
    CONF_SMTP_SENDER,
    CONF_SMTP_USERNAME,
    SECURITY_SSL,
    SECURITY_STARTTLS,
    SMTP_PORTS,
)

_TIMEOUT = 15


class MailError(Exception):
    """Sending failed; the message is the error code."""


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    """SMTP settings from the options flow."""

    host: str
    port: int
    security: str
    username: str | None
    password: str | None
    sender: str

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> SmtpConfig | None:
        """Return the settings, or None if email isn't set up."""
        if not (host := options.get(CONF_SMTP_HOST)):
            return None
        security = options.get(CONF_SMTP_SECURITY, SECURITY_STARTTLS)
        return cls(
            host=host,
            port=int(options.get(CONF_SMTP_PORT) or SMTP_PORTS[security]),
            security=security,
            username=options.get(CONF_SMTP_USERNAME) or None,
            password=options.get(CONF_SMTP_PASSWORD) or None,
            sender=options[CONF_SMTP_SENDER],
        )


class Mailer:
    """Send plain-text email. smtplib blocks, so it runs in the executor."""

    def __init__(self, hass: HomeAssistant, config: SmtpConfig) -> None:
        """Create the mailer."""
        self._hass = hass
        self._config = config

    async def async_test(self) -> None:
        """Connect and log in without sending. Raises MailError."""
        await self._hass.async_add_executor_job(self._test)

    async def async_send(self, to: str, subject: str, body: str) -> None:
        """Send an email. Raises MailError."""
        msg = EmailMessage()
        msg["From"] = self._config.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        await self._hass.async_add_executor_job(self._send, msg)

    def _test(self) -> None:
        with self._connect():
            pass

    def _send(self, msg: EmailMessage) -> None:
        with self._connect() as server:
            try:
                server.send_message(msg)
            except (OSError, smtplib.SMTPException) as err:
                raise MailError("smtp_send_failed") from err

    def _connect(self) -> smtplib.SMTP:
        config = self._config
        server: smtplib.SMTP | None = None
        try:
            if config.security == SECURITY_SSL:
                server = smtplib.SMTP_SSL(
                    config.host, config.port, timeout=_TIMEOUT, context=client_context()
                )
            else:
                server = smtplib.SMTP(config.host, config.port, timeout=_TIMEOUT)
                if config.security == SECURITY_STARTTLS:
                    server.starttls(context=client_context())
            if config.username:
                server.login(config.username, config.password or "")
        except smtplib.SMTPAuthenticationError as err:
            _close(server)
            raise MailError("smtp_auth_failed") from err
        except (OSError, smtplib.SMTPException) as err:
            _close(server)
            raise MailError("smtp_cannot_connect") from err
        return server


def _close(server: smtplib.SMTP | None) -> None:
    if server is not None:
        with suppress(OSError):
            server.close()
