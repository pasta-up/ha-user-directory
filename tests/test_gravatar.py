"""Tests for the Gravatar profile picture."""

from http import HTTPStatus
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.user_directory.gravatar import (
    gravatar_hash,
    person_collection,
)
from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
ORIGINAL = "/api/image/serve/original-picture/512x512"
EMAIL = "Ada@Example.com"
AVATAR = f"https://gravatar.com/avatar/{gravatar_hash(EMAIL)}"


@pytest.fixture
async def person(hass: HomeAssistant, hass_admin_user: User) -> dict[str, Any]:
    """A UI-managed person linked to the admin user, with a picture."""
    assert await async_setup_component(hass, "person", {})
    return await person_collection(hass).async_create_item(
        {
            "name": "Ada",
            "user_id": hass_admin_user.id,
            "picture": ORIGINAL,
            "device_trackers": ["device_tracker.ada_phone"],
        }
    )


def _picture(hass: HomeAssistant, person: dict[str, Any]) -> str | None:
    return person_collection(hass).data[person["id"]].get("picture")


async def _send(client, msg: dict[str, Any]) -> dict[str, Any]:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def _set_email(client, email: str | None) -> dict[str, Any]:
    return await _send(
        client, {"type": "user_directory/contact/update", "email": email}
    )


async def _set_gravatar(client, enabled: bool, **extra: Any) -> dict[str, Any]:
    return await _send(
        client,
        {"type": "user_directory/gravatar/set", "enabled": enabled, **extra},
    )


async def test_needs_person(
    hass: HomeAssistant, entry: MockConfigEntry, hass_ws_client: WebSocketGenerator
) -> None:
    """Without a linked person there's nowhere to put the picture."""
    assert await async_setup_component(hass, "person", {})
    client = await hass_ws_client(hass)
    msg = await _set_gravatar(client, True)
    assert msg["error"]["code"] == "no_person"


async def test_needs_email_and_gravatar(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Turning it on fails clearly without an email or a Gravatar."""
    client = await hass_ws_client(hass)
    assert (await _set_gravatar(client, True))["error"]["code"] == "no_email"

    await _set_email(client, EMAIL)
    aioclient_mock.get(AVATAR, status=HTTPStatus.NOT_FOUND)
    assert (await _set_gravatar(client, True))["error"]["code"] == "no_gravatar"
    assert _picture(hass, person) == ORIGINAL


async def test_enable_and_disable(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    hass_admin_user: User,
) -> None:
    """The Gravatar becomes the picture, is served locally, and off restores it."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    aioclient_mock.get(AVATAR, content=PNG)

    msg = await _set_gravatar(client, True)
    assert msg["result"]["gravatar"] == {"enabled": True, "available": True}
    picture = _picture(hass, person)
    assert picture.startswith(f"/api/user_directory/avatar/{hass_admin_user.id}?v=")
    stored = person_collection(hass).data[person["id"]]
    assert stored["device_trackers"] == ["device_tracker.ada_phone"]

    http = await hass_client_no_auth()
    resp = await http.get(picture)
    assert resp.status == HTTPStatus.OK
    assert resp.content_type == "image/png"
    assert await resp.read() == PNG

    msg = await _set_gravatar(client, False)
    assert msg["result"]["gravatar"]["enabled"] is False
    assert _picture(hass, person) == ORIGINAL
    assert (await http.get(picture)).status == HTTPStatus.NOT_FOUND


async def test_email_changes(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A new email fetches a new avatar; removing the email turns Gravatar off."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    aioclient_mock.get(AVATAR, content=PNG)
    await _set_gravatar(client, True)
    first = _picture(hass, person)

    other = "grace@example.com"
    aioclient_mock.get(
        f"https://gravatar.com/avatar/{gravatar_hash(other)}", content=JPEG
    )
    await _set_email(client, other)
    assert _picture(hass, person) != first

    msg = await _set_email(client, None)
    assert msg["result"]["gravatar"]["enabled"] is False
    assert _picture(hass, person) == ORIGINAL


async def test_hand_set_picture_kept(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A picture changed by hand after enabling isn't replaced when turning off."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    aioclient_mock.get(AVATAR, content=PNG)
    await _set_gravatar(client, True)

    await person_collection(hass).async_update_item(
        person["id"], {"picture": "/manual.png", "device_trackers": []}
    )
    await _set_gravatar(client, False)
    assert _picture(hass, person) == "/manual.png"


async def test_others_need_admin(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_admin_user: User,
    hass_read_only_access_token: str,
) -> None:
    """Non-admins can't change someone else's Gravatar setting."""
    client = await hass_ws_client(hass, hass_read_only_access_token)
    msg = await _set_gravatar(client, True, user_id=hass_admin_user.id)
    assert msg["error"]["code"] == "unauthorized"


async def test_remove_entry_restores(
    hass: HomeAssistant,
    person: dict[str, Any],
    entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Removing the integration puts the original picture back."""
    client = await hass_ws_client(hass)
    await _set_email(client, EMAIL)
    aioclient_mock.get(AVATAR, content=PNG)
    await _set_gravatar(client, True)

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _picture(hass, person) == ORIGINAL
