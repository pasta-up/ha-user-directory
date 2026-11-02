"""Tests for the WebSocket commands."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant


async def test_own_contact(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    """A user can set, read and clear their own contact info."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "user_directory/contact/get"})
    assert (await client.receive_json())["result"] == {
        "contact": {},
        "sso": [],
        "locked": [],
        "gravatar": {"enabled": False, "available": False},
        "email_verification": {"available": True, "verified": False, "pending": False},
        "listed": False,
        "listed_locked": False,
        "shared": [],
    }

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "email": "ada@example.com",
            "github": "@ada",
        }
    )
    assert (await client.receive_json())["result"]["contact"] == {
        "email": "ada@example.com",
        "github": "ada",
    }

    await client.send_json_auto_id(
        {"type": "user_directory/contact/update", "email": "nope"}
    )
    msg = await client.receive_json()
    assert msg["error"]["code"] == "invalid_format"

    # A failed update leaves the saved info alone.
    await client.send_json_auto_id({"type": "user_directory/contact/get"})
    assert (await client.receive_json())["result"]["contact"]["github"] == "ada"

    await client.send_json_auto_id(
        {"type": "user_directory/contact/update", "email": "", "github": None}
    )
    assert (await client.receive_json())["result"]["contact"] == {}


async def test_non_admin_limited_to_self(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    hass_read_only_user: User,
    hass_read_only_access_token: str,
) -> None:
    """A non-admin can only touch their own info."""
    client = await hass_ws_client(hass, hass_read_only_access_token)

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "user_id": hass_read_only_user.id,
            "phone": "+44 20 7946 0000",
        }
    )
    assert (await client.receive_json())["success"]

    for msg in (
        {"type": "user_directory/contact/get", "user_id": hass_admin_user.id},
        {
            "type": "user_directory/contact/update",
            "user_id": hass_admin_user.id,
            "email": "x@example.com",
        },
        {"type": "user_directory/contact/list"},
    ):
        await client.send_json_auto_id(msg)
        assert (await client.receive_json())["error"]["code"] == "unauthorized"


async def test_admin_manages_others(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_user: User,
) -> None:
    """An admin can read, change and list anyone's info."""
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "user_id": hass_read_only_user.id,
            "email": "bob@example.com",
        }
    )
    assert (await client.receive_json())["success"]

    await client.send_json_auto_id(
        {"type": "user_directory/contact/get", "user_id": hass_read_only_user.id}
    )
    assert (await client.receive_json())["result"]["contact"] == {
        "email": "bob@example.com"
    }

    await client.send_json_auto_id({"type": "user_directory/contact/list"})
    assert (await client.receive_json())["result"] == {
        hass_read_only_user.id: {"email": "bob@example.com"}
    }

    await client.send_json_auto_id(
        {"type": "user_directory/contact/get", "user_id": "missing"}
    )
    assert (await client.receive_json())["error"]["code"] == "not_found"
