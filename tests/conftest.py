"""Fixtures for ha-user-directory tests."""

from collections.abc import Awaitable, Callable, Generator
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.user_directory.const import DOMAIN
from homeassistant.core import HomeAssistant

SMTP = {
    "smtp_host": "mail.example.com",
    "smtp_security": "starttls",
    "smtp_sender": "ha@example.com",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@pytest.fixture
def smtp() -> Generator[MagicMock]:
    """A fake SMTP server; smtp.return_value.send_message records sent mail."""
    with patch("custom_components.user_directory.mail.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = smtp.return_value
        yield smtp


def sent_code(smtp: MagicMock) -> str:
    """Return the code in the last email sent."""
    msg = smtp.return_value.send_message.call_args.args[0]
    return re.search(r"\b\d{6}\b", msg.get_content()).group()


@pytest.fixture
async def entry(hass: HomeAssistant, smtp: MagicMock) -> MockConfigEntry:
    """Set up the integration, with email set up."""
    entry = MockConfigEntry(domain=DOMAIN, title="User-Directory", options=SMTP)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def verify_email(
    smtp: MagicMock,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a helper that verifies the saved email through the WebSocket API."""

    async def _verify(client, **extra: Any) -> dict[str, Any]:
        await client.send_json_auto_id(
            {"type": "user_directory/email/send_code", **extra}
        )
        assert (await client.receive_json())["success"]
        await client.send_json_auto_id(
            {"type": "user_directory/email/confirm", "code": sent_code(smtp), **extra}
        )
        return await client.receive_json()

    return _verify
