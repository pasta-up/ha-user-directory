"""WebSocket commands. Users manage their own contact info; admins manage anyone's."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.util.hass_dict import HassKey

from .const import CONF_EMAIL, CONTACT_FIELDS, DOMAIN, SOCIAL_FIELDS
from .directory import async_directory, is_listed, listed_locked
from .gravatar import DATA_GRAVATAR, GravatarError
from .store import ContactStore, InvalidContact, clean_contact
from .verify import (
    DATA_VERIFIER,
    VerifyError,
    verified_email,
    verified_email_getter,
)

DATA_STORE: HassKey[ContactStore] = HassKey(DOMAIN)

CONF_USER_ID = "user_id"
CONF_LISTED = "listed"
CONF_SHARED = "shared"


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the commands; safe to call again after a reload."""
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_update)
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_gravatar_set)
    websocket_api.async_register_command(hass, ws_directory)
    websocket_api.async_register_command(hass, ws_send_code)
    websocket_api.async_register_command(hass, ws_confirm_code)


async def _async_target(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> tuple[ContactStore, str] | None:
    """Return the store and the user to act on, or send an error and return None."""
    if (store := hass.data.get(DATA_STORE)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "ha-user-directory is not loaded"
        )
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


async def _async_result(
    hass: HomeAssistant, store: ContactStore, user_id: str
) -> dict[str, Any]:
    gravatar = hass.data[DATA_GRAVATAR]
    verifier = hass.data[DATA_VERIFIER]
    user = await hass.auth.async_get_user(user_id)
    assert user is not None
    contact = store.get(user_id)
    email = contact.get(CONF_EMAIL)
    return {
        "contact": contact,
        "sso": store.sso_fields(user_id),
        "locked": store.locked_fields(user_id),
        CONF_LISTED: is_listed(store, user),
        "listed_locked": listed_locked(store, user),
        CONF_SHARED: store.shared(user_id),
        "gravatar": {
            "enabled": gravatar.enabled(user_id),
            "available": gravatar.available(user_id),
        },
        "email_verification": {
            "available": verifier.available,
            "verified": verified_email(store, verifier, user_id) is not None,
            "pending": bool(email) and verifier.pending(user_id, email),
        },
    }


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
        connection.send_result(msg["id"], await _async_result(hass, *target))


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/contact/update",
        probatio.Optional(CONF_USER_ID): str,
        **{
            probatio.Optional(field): probatio.Any(str, None)
            for field in CONTACT_FIELDS
        },
        probatio.Optional(CONF_LISTED): bool,
        probatio.Optional(CONF_SHARED): [probatio.In(SOCIAL_FIELDS)],
    }
)
@websocket_api.async_response
async def ws_update(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Replace a user's contact info. Omitted or empty fields are cleared.

    listed/shared are optional; omitted means unchanged.
    """
    if not (target := await _async_target(hass, connection, msg)):
        return
    store, user_id = target
    user = await hass.auth.async_get_user(user_id)
    assert user is not None
    if msg.get(CONF_LISTED) is False and listed_locked(store, user):
        connection.send_error(
            msg["id"], "listed_locked", "An admin requires this user to be listed"
        )
        return
    try:
        contact = clean_contact(msg)
    except InvalidContact as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return

    oidc = store.oidc(user_id)
    for field in store.locked_fields(user_id):
        if field in contact and contact[field] != oidc[field]:
            connection.send_error(
                msg["id"], "field_locked", f"{field} is managed by SSO"
            )
            return
    # Values matching SSO aren't stored, so later SSO changes still show through.
    contact = {f: v for f, v in contact.items() if oidc.get(f) != v}

    await store.async_set(user_id, contact)
    if CONF_LISTED in msg or CONF_SHARED in msg:
        await store.async_set_settings(
            user_id, listed=msg.get(CONF_LISTED), shared=msg.get(CONF_SHARED)
        )
    # A new email means a new Gravatar; no verified email turns Gravatar off.
    await hass.data[DATA_GRAVATAR].async_refresh(
        verified_email_getter(store, hass.data[DATA_VERIFIER])
    )
    connection.send_result(msg["id"], await _async_result(hass, store, user_id))


@websocket_api.websocket_command({probatio.Required("type"): f"{DOMAIN}/contact/list"})
@websocket_api.require_admin
@callback
def ws_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return every user's contact info. Admins only."""
    if (store := hass.data.get(DATA_STORE)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "ha-user-directory is not loaded"
        )
        return
    connection.send_result(msg["id"], store.all())


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/gravatar/set",
        probatio.Optional(CONF_USER_ID): str,
        probatio.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def ws_gravatar_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Turn a user's Gravatar profile picture on or off."""
    if not (target := await _async_target(hass, connection, msg)):
        return
    store, user_id = target
    gravatar = hass.data[DATA_GRAVATAR]
    try:
        if msg["enabled"]:
            await gravatar.async_enable(
                user_id,
                store.get(user_id).get(CONF_EMAIL),
                verified=verified_email(store, hass.data[DATA_VERIFIER], user_id)
                is not None,
            )
        else:
            await gravatar.async_disable(user_id)
    except GravatarError as err:
        connection.send_error(msg["id"], str(err), _GRAVATAR_ERRORS[str(err)])
        return
    connection.send_result(msg["id"], await _async_result(hass, store, user_id))


_GRAVATAR_ERRORS = {
    "no_person": "No person is linked to this user, or it's defined in YAML",
    "no_email": "Add an email address first",
    "not_verified": "Verify your email address first",
    "no_gravatar": "This email has no Gravatar",
    "cannot_connect": "Can't reach Gravatar",
}


@websocket_api.websocket_command(
    {probatio.Required("type"): f"{DOMAIN}/directory/list"}
)
@websocket_api.async_response
async def ws_directory(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the directory: listed users and only the fields they publish."""
    if (store := hass.data.get(DATA_STORE)) is None:
        connection.send_error(
            msg["id"], "not_loaded", "ha-user-directory is not loaded"
        )
        return
    connection.send_result(
        msg["id"], await async_directory(hass, store, hass.data[DATA_VERIFIER])
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/email/send_code",
        probatio.Optional(CONF_USER_ID): str,
    }
)
@websocket_api.async_response
async def ws_send_code(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Email a verification code to the user's saved email."""
    if not (target := await _async_target(hass, connection, msg)):
        return
    store, user_id = target
    if not (email := store.get(user_id).get(CONF_EMAIL)):
        connection.send_error(msg["id"], "no_email", "Add an email address first")
        return
    if verified_email(store, hass.data[DATA_VERIFIER], user_id):
        connection.send_error(
            msg["id"], "already_verified", _VERIFY_ERRORS["already_verified"]
        )
        return
    try:
        await hass.data[DATA_VERIFIER].async_send_code(user_id, email)
    except VerifyError as err:
        connection.send_error(msg["id"], str(err), _VERIFY_ERRORS[str(err)])
        return
    connection.send_result(msg["id"], await _async_result(hass, store, user_id))


@websocket_api.websocket_command(
    {
        probatio.Required("type"): f"{DOMAIN}/email/confirm",
        probatio.Optional(CONF_USER_ID): str,
        probatio.Required("code"): str,
    }
)
@websocket_api.async_response
async def ws_confirm_code(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Check a code and mark the user's saved email verified."""
    if not (target := await _async_target(hass, connection, msg)):
        return
    store, user_id = target
    if not (email := store.get(user_id).get(CONF_EMAIL)):
        connection.send_error(msg["id"], "no_email", "Add an email address first")
        return
    try:
        await hass.data[DATA_VERIFIER].async_confirm(user_id, email, msg["code"])
    except VerifyError as err:
        connection.send_error(msg["id"], str(err), _VERIFY_ERRORS[str(err)])
        return
    connection.send_result(msg["id"], await _async_result(hass, store, user_id))


_VERIFY_ERRORS = {
    "not_configured": "Email verification isn't set up. Ask an admin.",
    "already_verified": "This email is already verified",
    "too_soon": "Wait a minute before asking for another code",
    "too_many_codes": "Too many codes sent. Try again in an hour.",
    "send_failed": "The email couldn't be sent. Ask an admin to check the email settings.",
    "no_code": "The code has expired. Ask for a new one.",
    "wrong_code": "That code isn't right",
    "too_many_attempts": "Too many wrong codes. Ask for a new one.",
}
