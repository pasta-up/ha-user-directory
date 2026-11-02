"""WebSocket commands. Users manage their own contact info; admins manage anyone's."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.util.hass_dict import HassKey

from .const import CONTACT_FIELDS, DOMAIN
from .store import ContactStore, InvalidContact, clean_contact

DATA_STORE: HassKey[ContactStore] = HassKey(DOMAIN)

CONF_USER_ID = "user_id"


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the commands; safe to call again after a reload."""
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_update)
    websocket_api.async_register_command(hass, ws_list)


async def _async_target(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> tuple[ContactStore, str] | None:
    """Return the store and the user to act on, or send an error and return None."""
    if (store := hass.data.get(DATA_STORE)) is None:
        connection.send_error(msg["id"], "not_loaded", "Profile Extender is not loaded")
        return None
    user_id: str = msg.get(CONF_USER_ID) or connection.user.id
    if user_id == connection.user.id:
        return store, user_id
    if not connection.user.is_admin:
        raise Unauthorized
    if await hass.auth.async_get_user(user_id) is None:
        connection.send_error(msg["id"], "not_found", "User not found")
        return None
    return store, user_id


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/contact/get",
        probatio.Optional(CONF_USER_ID): str,
    }
)
@websocket_api.async_response
async def ws_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return a user's contact info; defaults to the current user."""
    if target := await _async_target(hass, connection, msg):
        store, user_id = target
        connection.send_result(msg["id"], store.get(user_id))


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/contact/update",
        probatio.Optional(CONF_USER_ID): str,
        **{
            probatio.Optional(field): probatio.Any(str, None)
            for field in CONTACT_FIELDS
        },
    }
)
@websocket_api.async_response
async def ws_update(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Replace a user's contact info. Omitted or empty fields are cleared."""
    if not (target := await _async_target(hass, connection, msg)):
        return
    store, user_id = target
    try:
        contact = clean_contact(msg)
    except InvalidContact as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    await store.async_set(user_id, contact)
    connection.send_result(msg["id"], contact)


@websocket_api.websocket_command({probatio.Required("type"): f"{DOMAIN}/contact/list"})
@websocket_api.require_admin
@callback
def ws_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return every user's contact info. Admins only."""
    if (store := hass.data.get(DATA_STORE)) is None:
        connection.send_error(msg["id"], "not_loaded", "Profile Extender is not loaded")
        return
    connection.send_result(msg["id"], store.all())
