"""Tests for SSO contact sync via hass-oidc-auth and Authentik."""

import hashlib
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.user_directory.const import (
    CONF_AUTHENTIK_TOKEN,
    CONF_OIDC_ENABLED,
    CONF_OIDC_ENFORCE,
    CONF_OIDC_PROVIDER,
    DOMAIN,
)
from homeassistant.auth.models import Credentials, User
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

AUTHENTIK = "https://auth.example.com"
ISSUER = f"{AUTHENTIK}/application/o/home-assistant/"
DISCOVERY = f"{ISSUER}.well-known/openid-configuration"
USERS = f"{AUTHENTIK}/api/v3/core/users/"
ENABLED = {
    CONF_OIDC_ENABLED: True,
    CONF_OIDC_PROVIDER: "auth_oidc",
    CONF_AUTHENTIK_TOKEN: "secret",
    CONF_OIDC_ENFORCE: False,
}


@pytest.fixture
def auth_oidc(hass: HomeAssistant) -> None:
    """Pretend hass-oidc-auth is set up from the UI."""
    hass.auth._providers[("auth_oidc", "default")] = MagicMock()
    MockConfigEntry(domain="auth_oidc", data={"discovery_url": DISCOVERY}).add_to_hass(
        hass
    )


@pytest.fixture
def sso_user(hass: HomeAssistant, auth_oidc: None) -> User:
    """A user who signed in with SSO; Authentik uses the default subject mode."""
    user = MockUser(name="Ada").add_to_hass(hass)
    sub = hashlib.sha256(f"{ISSUER}.ada-uid".encode()).hexdigest()
    user.credentials.append(
        Credentials("auth_oidc", "default", {"sub": sub}, is_new=False)
    )
    return user


@pytest.fixture
def authentik(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock Authentik's discovery document and users API."""
    aioclient_mock.get(DISCOVERY, json={"issuer": ISSUER})
    aioclient_mock.get(
        f"{USERS}?page_size=1", json={"pagination": {"next": 0}, "results": []}
    )
    aioclient_mock.get(
        f"{USERS}?page_size=100",
        json={
            "pagination": {"next": 0},
            "results": [
                {
                    "pk": 1,
                    "uid": "ada-uid",
                    "username": "ada",
                    "email": "ada@sso.example",
                },
                {
                    "pk": 2,
                    "uid": "bob-uid",
                    "username": "bob",
                    "email": "bob@sso.example",
                },
            ],
        },
    )
    return aioclient_mock


async def _setup(hass: HomeAssistant, options: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _get(client, user: User) -> dict:
    await client.send_json_auto_id(
        {"type": "user_directory/contact/get", "user_id": user.id}
    )
    return (await client.receive_json())["result"]


async def _sso_step(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sso"}
    )


async def test_options_need_active_provider(hass: HomeAssistant) -> None:
    """SSO can't be turned on without a supported SSO integration."""
    entry = await _setup(hass, {})
    result = await _sso_step(hass, entry)
    assert result["description_placeholders"]["status"] == "not detected"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OIDC_ENABLED: True}
    )
    assert result["errors"] == {"base": "provider_not_active"}


async def test_options_validate_and_save(
    hass: HomeAssistant, auth_oidc: None, aioclient_mock: AiohttpClientMocker
) -> None:
    """The issuer comes from hass-oidc-auth, and the token is checked before saving."""
    entry = await _setup(hass, {})
    aioclient_mock.get(DISCOVERY, json={"issuer": "https://login.example.com/"})
    result = await _sso_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], ENABLED
    )
    assert result["errors"] == {"base": "unsupported_idp"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(DISCOVERY, json={"issuer": ISSUER})
    aioclient_mock.get(f"{USERS}?page_size=1", status=403)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], ENABLED
    )
    assert result["errors"] == {"base": "invalid_token"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(DISCOVERY, json={"issuer": ISSUER})
    aioclient_mock.get(f"{USERS}?page_size=1", json={"results": []})
    aioclient_mock.get(f"{USERS}?page_size=100", json={"results": []})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], ENABLED
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == ENABLED
    await hass.async_block_till_done()

    # Turning SSO off forgets the token.
    result = await _sso_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OIDC_ENABLED: False}
    )
    assert entry.options == {
        CONF_OIDC_ENABLED: False,
        CONF_OIDC_ENFORCE: False,
    }


async def test_sso_fills_empty_fields(
    hass: HomeAssistant,
    sso_user: User,
    authentik: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Without enforcement, SSO fills gaps and users can override it."""
    await _setup(hass, ENABLED)
    client = await hass_ws_client(hass)

    result = await _get(client, sso_user)
    assert result["contact"] == {"email": "ada@sso.example"}
    assert result["sso"] == ["email"]
    assert result["locked"] == []
    # The identity provider vouches for SSO emails.
    assert result["email_verification"]["verified"] is True

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "user_id": sso_user.id,
            "email": "ada@home.example",
        }
    )
    result = (await client.receive_json())["result"]
    assert result["contact"] == {"email": "ada@home.example"}
    assert result["email_verification"]["verified"] is False

    # Clearing the override shows the SSO value again.
    await client.send_json_auto_id(
        {"type": "user_directory/contact/update", "user_id": sso_user.id}
    )
    assert (await client.receive_json())["result"]["sso"] == ["email"]


async def test_sso_enforced(
    hass: HomeAssistant,
    sso_user: User,
    authentik: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """With enforcement, SSO fields are read-only; others stay editable."""
    await _setup(hass, {**ENABLED, CONF_OIDC_ENFORCE: True})
    client = await hass_ws_client(hass)
    assert (await _get(client, sso_user))["locked"] == ["email"]

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "user_id": sso_user.id,
            "email": "ada@home.example",
        }
    )
    assert (await client.receive_json())["error"]["code"] == "field_locked"

    await client.send_json_auto_id(
        {
            "type": "user_directory/contact/update",
            "user_id": sso_user.id,
            "email": "ada@sso.example",
            "phone": "+1 555 123 4567",
        }
    )
    assert (await client.receive_json())["result"]["contact"] == {
        "email": "ada@sso.example",
        "phone": "+1 555 123 4567",
    }


async def test_unmatched_users_untouched(
    hass: HomeAssistant,
    sso_user: User,
    authentik: AiohttpClientMocker,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_user: User,
) -> None:
    """Users without an SSO login get nothing from Authentik."""
    await _setup(hass, {**ENABLED, CONF_OIDC_ENFORCE: True})
    client = await hass_ws_client(hass)
    assert await _get(client, hass_read_only_user) == {
        "contact": {},
        "sso": [],
        "locked": [],
        "gravatar": {"enabled": False, "available": False},
        "email_verification": {"available": False, "verified": False, "pending": False},
        "listed": False,
        "listed_locked": False,
        "shared": [],
    }
