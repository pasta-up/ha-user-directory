"""Tests for email verification and its SMTP settings."""

import smtplib
from typing import Any
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.user_directory.const import DOMAIN
from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.http import current_request

from .conftest import SMTP, sent_code

EMAIL = "Ada@Example.com"


async def _send(client, msg: dict[str, Any]) -> dict[str, Any]:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _set_email(client, email: str | None) -> dict[str, Any]:
    return await _send(
        client, {"type": "user_directory/contact/update", "email": email}
    )


async def _send_code(client, **extra: Any) -> dict[str, Any]:
    return await _send(client, {"type": "user_directory/email/send_code", **extra})


async def _confirm(client, code: str, **extra: Any) -> dict[str, Any]:
    return await _send(
        client, {"type": "user_directory/email/confirm", "code": code, **extra}
    )


async def test_verify(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    smtp: MagicMock,
) -> None:
    """A code is emailed to the saved address, and entering it verifies it."""
    client = await hass_ws_client(hass)
    assert (await _send_code(client))["error"]["code"] == "no_email"

    msg = await _set_email(client, EMAIL)
    assert msg["result"]["email_verification"] == {
        "available": True,
        "verified": False,
        "pending": False,
    }

    msg = await _send_code(client)
    assert msg["result"]["email_verification"]["pending"] is True
    server = smtp.return_value
    server.starttls.assert_called_once()
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == EMAIL
    assert sent["From"] == SMTP["smtp_sender"]

    code = sent_code(smtp)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    assert (await _confirm(client, wrong))["error"]["code"] == "wrong_code"
    msg = await _confirm(client, code)
    assert msg["result"]["email_verification"] == {
        "available": True,
        "verified": True,
        "pending": False,
    }
    assert (await _send_code(client))["error"]["code"] == "already_verified"

    # Case doesn't matter, but a different address isn't verified.
    msg = await _set_email(client, EMAIL.lower())
    assert msg["result"]["email_verification"]["verified"] is True
    msg = await _set_email(client, "grace@example.com")
    assert msg["result"]["email_verification"]["verified"] is False


async def test_code_tied_to_email(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    smtp: MagicMock,
) -> None:
    """A code sent to one address can't verify another."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    await _send_code(client)
    await _set_email(client, "grace@example.com")
    msg = await _confirm(client, sent_code(smtp))
    assert msg["error"]["code"] == "no_code"


async def test_limits(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    smtp: MagicMock,
) -> None:
    """Codes expire, resends are rate-limited, and guesses are capped."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    now = 1000.0
    with patch(
        "custom_components.user_directory.verify.monotonic", side_effect=lambda: now
    ):
        await _send_code(client)
        assert (await _send_code(client))["error"]["code"] == "too_soon"

        for _ in range(4):
            assert (await _confirm(client, "wrong"))["error"]["code"] == "wrong_code"
        msg = await _confirm(client, "wrong")
        assert msg["error"]["code"] == "too_many_attempts"
        assert (await _confirm(client, sent_code(smtp)))["error"]["code"] == "no_code"

        now += 61
        await _send_code(client)
        now += 15 * 60
        assert (await _confirm(client, sent_code(smtp)))["error"]["code"] == "no_code"

        for _ in range(3):
            now += 61
            assert (await _send_code(client))["success"]
        now += 61
        msg = await _send_code(client)
        assert msg["error"]["code"] == "too_many_codes"


async def test_send_failure(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    smtp: MagicMock,
) -> None:
    """SMTP errors are reported without details."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    smtp.return_value.send_message.side_effect = smtplib.SMTPRecipientsRefused({})
    assert (await _send_code(client))["error"]["code"] == "send_failed"


async def test_not_configured(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Without SMTP settings, codes can't be sent."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    client = await hass_ws_client(hass)
    msg = await _set_email(client, EMAIL)
    assert msg["result"]["email_verification"]["available"] is False
    assert (await _send_code(client))["error"]["code"] == "not_configured"


async def test_others_need_admin(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    hass_read_only_access_token: str,
) -> None:
    """Non-admins can't send codes for, or verify, someone else."""
    client = await hass_ws_client(hass, hass_read_only_access_token)
    msg = await _send_code(client, user_id=hass_admin_user.id)
    assert msg["error"]["code"] == "unauthorized"
    msg = await _confirm(client, "123456", user_id=hass_admin_user.id)
    assert msg["error"]["code"] == "unauthorized"


async def test_directory_shows_verified(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    verify_email,
) -> None:
    """The directory marks verified emails."""
    client = await hass_ws_client(hass)
    await _send(
        client,
        {"type": "user_directory/contact/update", "email": EMAIL, "listed": True},
    )
    msg = await _send(client, {"type": "user_directory/directory/list"})
    assert msg["result"][0]["email_verified"] is False
    await verify_email(client)
    msg = await _send(client, {"type": "user_directory/directory/list"})
    assert msg["result"][0]["email_verified"] is True


async def _email_step(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "email"}
    )


async def test_options(hass: HomeAssistant, smtp: MagicMock) -> None:
    """SMTP settings are tested before saving, and the password is kept."""
    entry = MockConfigEntry(domain=DOMAIN, options={"publish_policy": "all"})
    entry.add_to_hass(hass)
    settings = {**SMTP, "smtp_username": "ha", "smtp_password": "secret"}

    result = await _email_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**settings, "smtp_sender": "nope"}
    )
    assert result["errors"] == {"smtp_sender": "invalid_email"}

    smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], settings
    )
    assert result["errors"] == {"base": "smtp_auth_failed"}

    smtp.return_value.login.side_effect = None
    smtp.side_effect = OSError
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], settings
    )
    assert result["errors"] == {"base": "smtp_cannot_connect"}

    smtp.side_effect = None
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], settings
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"publish_policy": "all", **settings}
    smtp.assert_called_with("mail.example.com", 587, timeout=15)
    smtp.return_value.login.assert_called_with("ha", "secret")
    await hass.async_block_till_done()

    # A blank password keeps the saved one.
    result = await _email_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**SMTP, "smtp_username": "ha", "smtp_port": 2525}
    )
    assert entry.options["smtp_password"] == "secret"
    assert entry.options["smtp_port"] == 2525
    await hass.async_block_till_done()

    # A blank server turns email off and forgets the settings.
    result = await _email_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"smtp_security": "starttls"}
    )
    assert entry.options == {"publish_policy": "all"}


async def test_send_test_email(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    smtp: MagicMock,
) -> None:
    """Admins can send a test email, to their own email by default."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)

    # Options flows don't record the user; the dialog's HTTP request does.
    token = current_request.set({"hass_user": hass_admin_user})
    try:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert "email_test" in result["menu_options"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "email_test"}
        )
    finally:
        current_request.reset(token)
    schema = result["data_schema"].schema
    assert next(iter(schema)).description == {"suggested_value": EMAIL}

    smtp.return_value.send_message.side_effect = smtplib.SMTPDataError(
        554, b"Sender rejected"
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"test_recipient": "grace@example.com"}
    )
    assert result["errors"] == {"base": "smtp_send_failed"}
    assert "Sender rejected" in result["description_placeholders"]["detail"]

    smtp.return_value.send_message.side_effect = None
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"test_recipient": "grace@example.com"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "test_sent"
    assert smtp.return_value.send_message.call_args.args[0]["To"] == (
        "grace@example.com"
    )


async def test_no_test_without_smtp(hass: HomeAssistant) -> None:
    """The test button only shows once email is set up."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "email_test" not in result["menu_options"]
