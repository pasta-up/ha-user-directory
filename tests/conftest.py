"""Fixtures for ha-user-directory tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.user_directory.const import DOMAIN
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up the integration."""
    entry = MockConfigEntry(domain=DOMAIN, title="User-Directory")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
