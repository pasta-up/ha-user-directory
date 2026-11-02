"""Who appears in the directory, and what they show. See agents.md "Directory"."""

from __future__ import annotations

from typing import Any

from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EMAIL,
    CONF_PHONE,
    POLICY_ALL,
    POLICY_OIDC,
    PROVIDER_AUTH_OIDC,
    SOCIAL_FIELDS,
)
from .store import ContactStore


def is_oidc_user(user: User) -> bool:
    """Return whether the user signs in with hass-oidc-auth."""
    return any(c.auth_provider_type == PROVIDER_AUTH_OIDC for c in user.credentials)


def listed_locked(store: ContactStore, user: User) -> bool:
    """Return whether the admin's policy forces the user into the directory."""
    return store.policy == POLICY_ALL or (
        store.policy == POLICY_OIDC and is_oidc_user(user)
    )


def is_listed(store: ContactStore, user: User) -> bool:
    """Return whether the user appears in the directory."""
    return listed_locked(store, user) or store.listed_choice(user.id)


async def async_directory(
    hass: HomeAssistant, store: ContactStore
) -> list[dict[str, Any]]:
    """Return listed users with only the fields they publish, sorted by name."""
    pictures = {
        state.attributes.get("user_id"): state.attributes.get("entity_picture")
        for state in hass.states.async_all("person")
    }
    entries = []
    for user in await hass.auth.async_get_users():
        if user.system_generated or not user.is_active or not is_listed(store, user):
            continue
        contact = store.get(user.id)
        shared = store.shared(user.id)
        entry: dict[str, Any] = {
            "user_id": user.id,
            "name": user.name or "",
            "picture": pictures.get(user.id),
        }
        for field in (CONF_EMAIL, CONF_PHONE):
            if field in contact:
                entry[field] = contact[field]
        for field in SOCIAL_FIELDS:
            if field in shared and field in contact:
                entry[field] = contact[field]
        entries.append(entry)
    return sorted(entries, key=lambda e: e["name"].casefold())
