"""Let Home Assistant users keep their own contact info and Gravatar."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from pathlib import Path

from homeassistant.auth import EVENT_USER_ADDED, EVENT_USER_REMOVED
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    CONF_AUTHENTIK_TOKEN,
    CONF_EMAIL,
    CONF_OIDC_ENABLED,
    CONF_OIDC_ENFORCE,
    DOMAIN,
    GRAVATAR_REFRESH_INTERVAL,
    OIDC_SYNC_INTERVAL,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_URL,
)
from .gravatar import DATA_GRAVATAR, AvatarView, GravatarManager
from .oidc import AuthentikSync, OidcError
from .store import ContactStore
from .websocket import DATA_STORE, async_register_commands

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the panel's JS and avatars. These can't be unregistered, so this runs once."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), False)]
    )
    hass.http.register_view(AvatarView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load data, start background syncs, and add the sidebar panel."""
    oidc_enabled = entry.options.get(CONF_OIDC_ENABLED, False)
    store = ContactStore(
        hass, enforce_oidc=oidc_enabled and entry.options.get(CONF_OIDC_ENFORCE, False)
    )
    await store.async_load()
    gravatar = GravatarManager(hass)
    await gravatar.async_load()
    hass.data[DATA_STORE] = store
    hass.data[DATA_GRAVATAR] = gravatar
    async_register_commands(hass)

    async def _async_user_removed(event: Event) -> None:
        await store.async_remove_user(event.data["user_id"])
        await gravatar.async_remove_user(event.data["user_id"])

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_USER_REMOVED, _async_user_removed)
    )

    async def _async_refresh_gravatar(_: datetime) -> None:
        await gravatar.async_refresh(
            lambda user_id: store.get(user_id).get(CONF_EMAIL), force=True
        )

    entry.async_on_unload(
        async_track_time_interval(
            hass, _async_refresh_gravatar, GRAVATAR_REFRESH_INTERVAL
        )
    )

    if oidc_enabled:
        _async_start_oidc_sync(hass, entry, store, gravatar)
    else:
        await store.async_clear_oidc()

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


def _async_start_oidc_sync(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: ContactStore,
    gravatar: GravatarManager,
) -> None:
    """Sync now, hourly, and when a user is added (first SSO login)."""
    sync = AuthentikSync(hass, entry.options[CONF_AUTHENTIK_TOKEN])
    lock = asyncio.Lock()

    async def _async_sync(_: datetime | Event | None = None) -> None:
        async with lock:
            try:
                await store.async_set_oidc(await sync.async_fetch())
            except OidcError as err:
                # Keep the last known SSO values rather than unlocking fields.
                _LOGGER.warning("SSO contact sync failed: %s", err)
                return
        # An SSO email change should change the Gravatar too.
        await gravatar.async_refresh(lambda user_id: store.get(user_id).get(CONF_EMAIL))

    entry.async_on_unload(
        async_track_time_interval(hass, _async_sync, OIDC_SYNC_INTERVAL)
    )
    entry.async_on_unload(hass.bus.async_listen(EVENT_USER_ADDED, _async_sync))
    entry.async_create_background_task(hass, _async_sync(), f"{DOMAIN} SSO sync")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the panel. Pictures stay as they are."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    hass.data.pop(DATA_STORE, None)
    hass.data.pop(DATA_GRAVATAR, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete everything and put back pictures replaced by Gravatar."""
    await ContactStore(hass).async_remove()
    gravatar = GravatarManager(hass)
    await gravatar.async_load()
    await gravatar.async_remove_all()
