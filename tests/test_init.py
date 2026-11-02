"""Tests for setup, unload and cleanup."""

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.profile_extender.const import PANEL_URL_PATH, STORAGE_KEY
from custom_components.profile_extender.websocket import DATA_STORE
from homeassistant.auth.models import User
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import HomeAssistant


async def test_panel_added_and_removed(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """The panel exists while the entry is loaded."""
    panel = hass.data[DATA_PANELS][PANEL_URL_PATH]
    assert panel.require_admin is False

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_URL_PATH not in hass.data[DATA_PANELS]
    assert DATA_STORE not in hass.data


async def test_user_removed(
    hass: HomeAssistant, entry: MockConfigEntry, hass_read_only_user: User
) -> None:
    """Deleting a user deletes their contact info."""
    store = hass.data[DATA_STORE]
    await store.async_set(hass_read_only_user.id, {"email": "bob@example.com"})

    await hass.auth.async_remove_user(hass_read_only_user)
    await hass.async_block_till_done()
    assert store.all() == {}


async def test_remove_entry_deletes_storage(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_storage: dict[str, Any],
    hass_read_only_user: User,
) -> None:
    """Removing the integration deletes the storage file."""
    await hass.data[DATA_STORE].async_set(hass_read_only_user.id, {"github": "bob"})
    assert STORAGE_KEY in hass_storage

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert STORAGE_KEY not in hass_storage
