"""Tests for the directory and its publishing policy."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.user_directory.const import (
    CONF_PUBLISH_POLICY,
    DOMAIN,
    POLICY_ALL,
    POLICY_CHOICE,
    POLICY_OIDC,
)
from homeassistant.auth.models import Credentials, User
from homeassistant.core import HomeAssistant

ADA = {"email": "ada@example.com", "phone": "+1 555 123 4567", "github": "ada"}


async def _setup(hass: HomeAssistant, policy: str) -> None:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_PUBLISH_POLICY: policy})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _send(client, msg: dict[str, Any]) -> dict[str, Any]:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _directory(client) -> list[dict[str, Any]]:
    return (await _send(client, {"type": "user_directory/directory/list"}))["result"]


@pytest.fixture
def sso_user(hass: HomeAssistant) -> User:
    """A user who signs in with hass-oidc-auth."""
    user = MockUser(name="Sso").add_to_hass(hass)
    user.credentials.append(
        Credentials("auth_oidc", "default", {"sub": "x"}, is_new=False)
    )
    return user


async def test_opt_in_and_socials(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    hass_read_only_access_token: str,
) -> None:
    """Users are hidden until they opt in, and socials need their own opt-in."""
    await _setup(hass, POLICY_CHOICE)
    admin = await hass_ws_client(hass)
    reader = await hass_ws_client(hass, hass_read_only_access_token)

    msg = await _send(admin, {"type": "user_directory/contact/update", **ADA})
    assert msg["result"]["listed"] is False
    assert msg["result"]["listed_locked"] is False
    assert await _directory(reader) == []

    await _send(admin, {"type": "user_directory/contact/update", **ADA, "listed": True})
    entry = (await _directory(reader))[0]
    assert entry["user_id"] == hass_admin_user.id
    assert entry["email"] == ADA["email"]
    assert entry["phone"] == ADA["phone"]
    # GitHub stays private until shared.
    assert "github" not in entry

    await _send(
        admin,
        {"type": "user_directory/contact/update", **ADA, "shared": ["github"]},
    )
    assert (await _directory(reader))[0]["github"] == "ada"

    msg = await _send(
        admin,
        {"type": "user_directory/contact/update", **ADA, "shared": ["email"]},
    )
    assert msg["success"] is False


async def test_policy_all(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    hass_read_only_user: User,
) -> None:
    """With "all", everyone is listed and can't opt out."""
    await _setup(hass, POLICY_ALL)
    client = await hass_ws_client(hass)
    names = {e["user_id"] for e in await _directory(client)}
    assert {hass_admin_user.id, hass_read_only_user.id} <= names

    msg = await _send(
        client, {"type": "user_directory/contact/update", "listed": False}
    )
    assert msg["error"]["code"] == "listed_locked"


async def test_policy_oidc(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    sso_user: User,
) -> None:
    """With "oidc", SSO users are always listed; others still choose."""
    await _setup(hass, POLICY_OIDC)
    client = await hass_ws_client(hass)
    assert [e["user_id"] for e in await _directory(client)] == [sso_user.id]

    msg = await _send(
        client,
        {
            "type": "user_directory/contact/get",
            "user_id": sso_user.id,
        },
    )
    assert msg["result"]["listed_locked"] is True

    await _send(client, {"type": "user_directory/contact/update", "listed": True})
    ids = {e["user_id"] for e in await _directory(client)}
    assert ids == {sso_user.id, hass_admin_user.id}


async def test_system_users_hidden(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """System-generated users never appear."""
    await _setup(hass, POLICY_ALL)
    await hass.auth.async_create_system_user("Supervisor")
    client = await hass_ws_client(hass)
    assert "Supervisor" not in {e["name"] for e in await _directory(client)}
