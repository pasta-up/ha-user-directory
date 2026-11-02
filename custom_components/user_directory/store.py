"""Per-user contact info storage and validation."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_EMAIL,
    CONF_GITHUB,
    CONF_PHONE,
    CONTACT_FIELDS,
    POLICY_CHOICE,
    STORAGE_KEY,
    STORAGE_KEY_OIDC,
    STORAGE_KEY_SETTINGS,
    STORAGE_VERSION,
)

type Contact = dict[str, str]

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?[\d\s().-]+")
# GitHub's own rule: alphanumerics and single inner hyphens, at most 39 chars.
_GITHUB = re.compile(r"[A-Za-z\d](?:-?[A-Za-z\d]){0,38}")


class InvalidContact(ValueError):
    """A contact field has an invalid value."""

    def __init__(self, field: str) -> None:
        """Remember which field failed."""
        super().__init__(f"Invalid {field}")
        self.field = field


def clean_contact(values: dict[str, str | None]) -> Contact:
    """Return the non-empty fields, normalised. Raise InvalidContact on bad input."""
    contact: Contact = {}
    for field in CONTACT_FIELDS:
        value = (values.get(field) or "").strip()
        if not value:
            continue
        if field == CONF_GITHUB:
            value = value.removeprefix("@")
        if not _is_valid(field, value):
            raise InvalidContact(field)
        contact[field] = value
    return contact


def _is_valid(field: str, value: str) -> bool:
    if field == CONF_EMAIL:
        return len(value) <= 254 and _EMAIL.fullmatch(value) is not None
    if field == CONF_PHONE:
        return (
            _PHONE.fullmatch(value) is not None
            and 7 <= sum(c.isdigit() for c in value) <= 15
        )
    return _GITHUB.fullmatch(value) is not None


class ContactStore:
    """Contact info keyed by user ID: what users entered, and what SSO provided."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        enforce_oidc: bool = False,
        policy: str = POLICY_CHOICE,
    ) -> None:
        """Create the store; call async_load before use."""
        # private=True keeps the files readable by the HA user only.
        self._manual_store: Store[dict[str, Contact]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, private=True
        )
        self._oidc_store: Store[dict[str, Contact]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_OIDC, private=True
        )
        # {user_id: {"listed": bool, "shared": [social fields]}}
        self._settings_store: Store[dict[str, dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_SETTINGS, private=True
        )
        self._manual: dict[str, Contact] = {}
        self._oidc: dict[str, Contact] = {}
        self._settings: dict[str, dict[str, Any]] = {}
        self.enforce_oidc = enforce_oidc
        self.policy = policy

    async def async_load(self) -> None:
        """Load saved contacts."""
        self._manual = await self._manual_store.async_load() or {}
        self._oidc = await self._oidc_store.async_load() or {}
        self._settings = await self._settings_store.async_load() or {}

    def listed_choice(self, user_id: str) -> bool:
        """Return whether the user chose to be listed. Policy may override; see directory.py."""
        return self._settings.get(user_id, {}).get("listed", False)

    def shared(self, user_id: str) -> list[str]:
        """Return the social fields the user shows in the directory."""
        return list(self._settings.get(user_id, {}).get("shared", []))

    async def async_set_settings(
        self,
        user_id: str,
        *,
        listed: bool | None = None,
        shared: list[str] | None = None,
    ) -> None:
        """Update a user's directory settings; None leaves a value unchanged."""
        settings = self._settings.setdefault(user_id, {})
        if listed is not None:
            settings["listed"] = listed
        if shared is not None:
            settings["shared"] = shared
        await self._settings_store.async_save(self._settings)

    def get(self, user_id: str) -> Contact:
        """Return a user's contact info. SSO fills gaps, or wins when enforced."""
        manual = self._manual.get(user_id, {})
        oidc = self._oidc.get(user_id, {})
        return {**manual, **oidc} if self.enforce_oidc else {**oidc, **manual}

    def sso_fields(self, user_id: str) -> list[str]:
        """Return the fields currently showing an SSO value."""
        contact = self.get(user_id)
        oidc = self._oidc.get(user_id, {})
        return [f for f in CONTACT_FIELDS if f in oidc and contact.get(f) == oidc[f]]

    def locked_fields(self, user_id: str) -> list[str]:
        """Return the fields nobody can edit in Home Assistant."""
        return list(self._oidc.get(user_id, {})) if self.enforce_oidc else []

    def oidc(self, user_id: str) -> Contact:
        """Return what SSO provided for a user."""
        return dict(self._oidc.get(user_id, {}))

    def all(self) -> dict[str, Contact]:
        """Return every user's contact info."""
        return {user_id: self.get(user_id) for user_id in self._manual | self._oidc}

    async def async_set(self, user_id: str, contact: Contact) -> None:
        """Replace what a user entered; an empty contact removes the user."""
        if contact:
            self._manual[user_id] = contact
        elif self._manual.pop(user_id, None) is None:
            return
        await self._manual_store.async_save(self._manual)

    async def async_set_oidc(self, contacts: dict[str, Contact]) -> None:
        """Replace everything SSO provided."""
        if contacts != self._oidc:
            self._oidc = contacts
            await self._oidc_store.async_save(self._oidc)

    async def async_remove_user(self, user_id: str) -> None:
        """Forget a user."""
        await self.async_set(user_id, {})
        if self._settings.pop(user_id, None) is not None:
            await self._settings_store.async_save(self._settings)
        if user_id in self._oidc:
            await self.async_set_oidc(
                {uid: c for uid, c in self._oidc.items() if uid != user_id}
            )

    async def async_clear_oidc(self) -> None:
        """Forget everything SSO provided."""
        self._oidc = {}
        await self._oidc_store.async_remove()

    async def async_remove(self) -> None:
        """Delete both storage files."""
        self._manual = {}
        await self._manual_store.async_remove()
        self._settings = {}
        await self._settings_store.async_remove()
        await self.async_clear_oidc()
