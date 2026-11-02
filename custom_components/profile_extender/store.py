"""Per-user contact info storage and validation."""

from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_EMAIL,
    CONF_GITHUB,
    CONF_PHONE,
    CONTACT_FIELDS,
    STORAGE_KEY,
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
    """Contact info keyed by Home Assistant user ID."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the store; call async_load before use."""
        # private=True keeps the file readable by the HA user only.
        self._store: Store[dict[str, Contact]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, private=True
        )
        self._data: dict[str, Contact] = {}

    async def async_load(self) -> None:
        """Load saved contacts."""
        self._data = await self._store.async_load() or {}

    def get(self, user_id: str) -> Contact:
        """Return a user's contact info."""
        return dict(self._data.get(user_id, {}))

    def all(self) -> dict[str, Contact]:
        """Return every user's contact info."""
        return {user_id: dict(contact) for user_id, contact in self._data.items()}

    async def async_set(self, user_id: str, contact: Contact) -> None:
        """Replace a user's contact info; an empty contact removes the user."""
        if contact:
            self._data[user_id] = contact
        elif self._data.pop(user_id, None) is None:
            return
        await self._store.async_save(self._data)

    async def async_remove(self) -> None:
        """Delete the storage file."""
        self._data = {}
        await self._store.async_remove()
