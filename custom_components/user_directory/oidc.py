"""Read contact info from the SSO identity provider. See agents.md "SSO"."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EMAIL, PROVIDER_AUTH_OIDC, SUPPORTED_PROVIDERS
from .store import Contact, InvalidContact, clean_contact

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_AUTHENTIK_ISSUER_PATH = "/application/o/"


class OidcError(Exception):
    """Base error; the message is the translation key."""


class CannotConnect(OidcError):
    """The identity provider can't be reached."""

    def __init__(self) -> None:
        """Set the translation key."""
        super().__init__("cannot_connect")


class InvalidToken(OidcError):
    """The API token was rejected."""

    def __init__(self) -> None:
        """Set the translation key."""
        super().__init__("invalid_token")


class UnsupportedIdp(OidcError):
    """The identity provider isn't one we can query."""

    def __init__(self) -> None:
        """Set the translation key."""
        super().__init__("unsupported_idp")


class ProviderNotActive(OidcError):
    """The login integration isn't set up."""

    def __init__(self) -> None:
        """Set the translation key."""
        super().__init__("provider_not_active")


def active_providers(hass: HomeAssistant) -> dict[str, str]:
    """Return supported login integrations that are registered as an auth provider."""
    return {
        key: label
        for key, label in SUPPORTED_PROVIDERS.items()
        if hass.auth.get_auth_providers(key)
    }


def _discovery_url(hass: HomeAssistant) -> str | None:
    # hass-oidc-auth keeps this in its config entry (UI) or hass.data (YAML).
    for entry in hass.config_entries.async_entries(PROVIDER_AUTH_OIDC):
        if url := entry.data.get("discovery_url"):
            return url
    yaml = hass.data.get(PROVIDER_AUTH_OIDC, {}).get("yaml_config", {})
    return yaml.get("discovery_url")


class AuthentikSync:
    """Fetch emails from Authentik for users who sign in with hass-oidc-auth."""

    def __init__(self, hass: HomeAssistant, token: str) -> None:
        """Store the token; call async_connect before syncing."""
        self._hass = hass
        self._session = async_get_clientsession(hass)
        self._token = token
        self.issuer: str | None = None
        self.api_url: str | None = None

    async def async_connect(self) -> None:
        """Find the issuer and API from hass-oidc-auth's discovery URL, then check the token."""
        if not active_providers(self._hass) or not (url := _discovery_url(self._hass)):
            raise ProviderNotActive
        discovery = await self._async_get_json(url, auth=False)
        issuer = discovery.get("issuer")
        if not isinstance(issuer, str) or _AUTHENTIK_ISSUER_PATH not in issuer:
            raise UnsupportedIdp
        self.issuer = issuer
        self.api_url = issuer.split(_AUTHENTIK_ISSUER_PATH)[0] + "/api/v3"
        await self._async_get_json(f"{self.api_url}/core/users/?page_size=1")

    async def async_fetch(self) -> dict[str, Contact]:
        """Return SSO contact info keyed by Home Assistant user ID."""
        if self.issuer is None:
            await self.async_connect()
        assert self.issuer is not None
        subjects = await self._async_ha_subjects()
        contacts: dict[str, Contact] = {}
        async for user in self._async_users():
            if (user_id := self._match(user, subjects)) is None:
                continue
            try:
                contact = clean_contact({CONF_EMAIL: user.get("email")})
            except InvalidContact:
                _LOGGER.debug("Ignoring invalid email for %s", user.get("username"))
                continue
            if contact:
                contacts[user_id] = contact
        return contacts

    async def _async_ha_subjects(self) -> dict[str, str]:
        # hass-oidc-auth stores sha256("<issuer>.<sub>") on each user's credential.
        return {
            cred.data["sub"]: user.id
            for user in await self._hass.auth.async_get_users()
            for cred in user.credentials
            if cred.auth_provider_type == PROVIDER_AUTH_OIDC and "sub" in cred.data
        }

    def _match(self, user: dict[str, Any], subjects: dict[str, str]) -> str | None:
        # Authentik's subject mode decides what "sub" is; try each, default first.
        for candidate in (
            user.get("uid"),
            user.get("pk"),
            user.get("username"),
            user.get("email"),
        ):
            if candidate in (None, ""):
                continue
            digest = hashlib.sha256(f"{self.issuer}.{candidate}".encode()).hexdigest()
            if digest in subjects:
                return subjects[digest]
        return None

    async def _async_users(self):
        url: str | None = f"{self.api_url}/core/users/?page_size=100"
        while url:
            data = await self._async_get_json(url)
            for user in data.get("results", []):
                yield user
            next_page = data.get("pagination", {}).get("next")
            url = (
                f"{self.api_url}/core/users/?page_size=100&page={next_page}"
                if next_page
                else None
            )

    async def _async_get_json(self, url: str, *, auth: bool = True) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"} if auth else {}
        try:
            async with self._session.get(
                url, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidToken
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect from err
