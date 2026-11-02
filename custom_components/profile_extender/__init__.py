"""Let Home Assistant users keep their own contact info."""

from __future__ import annotations

from pathlib import Path

from homeassistant.auth import EVENT_USER_REMOVED
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_URL,
)
from .store import ContactStore
from .websocket import DATA_STORE, async_register_commands

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the panel's JS. Static paths can't be unregistered, so this runs once."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load contacts and add the sidebar panel."""
    store = ContactStore(hass)
    await store.async_load()
    hass.data[DATA_STORE] = store
    async_register_commands(hass)

    async def _async_user_removed(event: Event) -> None:
        await store.async_set(event.data["user_id"], {})

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_USER_REMOVED, _async_user_removed)
    )

    version = (await async_get_integration(hass, DOMAIN)).version
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        # ?v= busts the browser cache after an update.
        module_url=f"{STATIC_URL}/{PANEL_COMPONENT}.js?v={version}",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    hass.data.pop(DATA_STORE, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete everyone's contact info when the integration is removed."""
    await ContactStore(hass).async_remove()
