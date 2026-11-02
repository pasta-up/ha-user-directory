"""Use a user's Gravatar as their profile picture. See agents.md "Gravatar"."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from http import HTTPStatus
import logging
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.person import (
    DOMAIN as PERSON_DOMAIN,
    PersonStorageCollection,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import (
    AVATAR_URL,
    DOMAIN,
    GRAVATAR_SIZE,
    GRAVATAR_URL,
    STORAGE_KEY_GRAVATAR,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

_PICTURE = "picture"
_DEVICE_TRACKERS = "device_trackers"
_EMAIL = "email"
_ORIGINAL = "original_picture"

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class GravatarError(Exception):
    """Base error; the message is the WebSocket error code."""


class NoPerson(GravatarError):
    """The user has no UI-managed person to put the picture on."""

    def __init__(self) -> None:
        """Set the error code."""
        super().__init__("no_person")


class NoEmail(GravatarError):
    """The user has no email address."""

    def __init__(self) -> None:
        """Set the error code."""
        super().__init__("no_email")


class NotVerified(GravatarError):
    """The email isn't verified."""

    def __init__(self) -> None:
        """Set the error code."""
        super().__init__("not_verified")


class NoGravatar(GravatarError):
    """The email has no Gravatar."""

    def __init__(self) -> None:
        """Set the error code."""
        super().__init__("no_gravatar")


class CannotConnect(GravatarError):
    """Gravatar can't be reached."""

    def __init__(self) -> None:
        """Set the error code."""
        super().__init__("cannot_connect")


@dataclass(slots=True)
class Avatar:
    """An avatar image held in memory."""

    content: bytes
    content_type: str

    @property
    def digest(self) -> str:
        """Short content hash, used to bust browser caches when the image changes."""
        return hashlib.sha256(self.content).hexdigest()[:16]


def gravatar_hash(email: str) -> str:
    """Return the Gravatar hash for an email address."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def sniff_content_type(content: bytes) -> str | None:
    """Return the image type of content, or None if it is not a supported image."""
    for magic, content_type in _MAGIC:
        if content.startswith(magic):
            return content_type
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def person_collection(hass: HomeAssistant) -> PersonStorageCollection:
    """Return the collection of UI-managed persons."""
    data = hass.data[PERSON_DOMAIN]
    # Up to 2026.11 this is a (yaml, storage, entities) tuple, later a dataclass.
    if isinstance(data, tuple):
        return data[1]
    return data.storage_collection


def person_for_user(hass: HomeAssistant, user_id: str) -> dict[str, Any] | None:
    """Return the UI-managed person linked to a user. YAML persons can't be changed."""
    for person in person_collection(hass).async_items():
        if person.get("user_id") == user_id:
            return person
    return None


def avatar_url(user_id: str, avatar: Avatar) -> str:
    """Return the local URL a person's picture is set to."""
    return f"{AVATAR_URL.format(user_id=user_id)}?v={avatar.digest}"


def is_our_picture(user_id: str, picture: str | None) -> bool:
    """Return whether picture is one we set for the user."""
    return picture is not None and picture.startswith(
        AVATAR_URL.format(user_id=user_id)
    )


class GravatarManager:
    """Per-user Gravatar setting, cached avatars, and the person pictures they set."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the manager; call async_load before use."""
        self._hass = hass
        # {user_id: {"email": used for the avatar, "original_picture": to restore}}
        self._store: Store[dict[str, dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_GRAVATAR, private=True
        )
        self._folder = Path(hass.config.path(".storage", DOMAIN, "avatars"))
        self._users: dict[str, dict[str, Any]] = {}
        self._avatars: dict[str, Avatar] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load settings and cached avatars."""
        self._users = await self._store.async_load() or {}
        for user_id in self._users:
            content = await self._hass.async_add_executor_job(
                _read_file, self._folder / user_id
            )
            if content and (content_type := sniff_content_type(content)):
                self._avatars[user_id] = Avatar(content, content_type)

    def enabled(self, user_id: str) -> bool:
        """Return whether a user has Gravatar turned on."""
        return user_id in self._users

    def available(self, user_id: str) -> bool:
        """Return whether a user has a person we can put a picture on."""
        return person_for_user(self._hass, user_id) is not None

    def avatar(self, user_id: str) -> Avatar | None:
        """Return a user's cached avatar."""
        return self._avatars.get(user_id)

    async def async_enable(
        self, user_id: str, email: str | None, *, verified: bool
    ) -> None:
        """Turn Gravatar on and apply it now. Raises GravatarError if it can't."""
        async with self._lock:
            if person_for_user(self._hass, user_id) is None:
                raise NoPerson
            if not email:
                raise NoEmail
            if not verified:
                raise NotVerified
            avatar = await self._async_fetch(email)
            if avatar is None:
                raise NoGravatar
            self._users.setdefault(user_id, {})[_EMAIL] = email
            await self._async_apply(user_id, avatar)

    async def async_disable(self, user_id: str) -> None:
        """Turn Gravatar off, restoring the old picture unless it was changed since."""
        async with self._lock:
            if (settings := self._users.pop(user_id, None)) is None:
                return
            person = person_for_user(self._hass, user_id)
            if person is not None and is_our_picture(user_id, person.get(_PICTURE)):
                await _async_set_picture(self._hass, person, settings.get(_ORIGINAL))
            self._avatars.pop(user_id, None)
            await self._hass.async_add_executor_job(
                (self._folder / user_id).unlink, True
            )
            await self._store.async_save(self._users)

    async def async_refresh(
        self, email_for: Callable[[str], str | None], *, force: bool = False
    ) -> None:
        """Re-fetch avatars for enabled users; without force, only if their email changed.

        email_for returns the user's verified email, or None.
        """
        for user_id in list(self._users):
            email = email_for(user_id)
            if not email:
                # No verified email any more, so no Gravatar.
                await self.async_disable(user_id)
                continue
            if not force and self._users[user_id].get(_EMAIL) == email:
                continue
            async with self._lock:
                try:
                    avatar = await self._async_fetch(email)
                except CannotConnect:
                    _LOGGER.warning("Can't reach Gravatar, keeping the last avatar")
                    continue
                if avatar is None:
                    _LOGGER.warning(
                        "No Gravatar for user %s, keeping the picture", user_id
                    )
                    continue
                if user_id in self._users:
                    self._users[user_id][_EMAIL] = email
                    await self._async_apply(user_id, avatar)

    async def async_remove_user(self, user_id: str) -> None:
        """Forget a deleted user. Their person's picture is left alone."""
        if self._users.pop(user_id, None) is not None:
            self._avatars.pop(user_id, None)
            await self._hass.async_add_executor_job(
                (self._folder / user_id).unlink, True
            )
            await self._store.async_save(self._users)

    async def async_remove_all(self) -> None:
        """Turn Gravatar off for everyone and delete all files."""
        for user_id in list(self._users):
            await self.async_disable(user_id)
        await self._store.async_remove()

    async def _async_apply(self, user_id: str, avatar: Avatar) -> None:
        """Cache the avatar and point the person's picture at it."""
        self._avatars[user_id] = avatar
        await self._hass.async_add_executor_job(
            _write_file, self._folder / user_id, avatar.content
        )
        person = person_for_user(self._hass, user_id)
        if person is not None:
            current = person.get(_PICTURE)
            if not is_our_picture(user_id, current):
                self._users[user_id][_ORIGINAL] = current
            await _async_set_picture(self._hass, person, avatar_url(user_id, avatar))
        await self._store.async_save(self._users)

    async def _async_fetch(self, email: str) -> Avatar | None:
        """Download the avatar, or return None if the email has no Gravatar."""
        url = GRAVATAR_URL.format(hash=gravatar_hash(email))
        try:
            async with async_get_clientsession(self._hass).get(
                url,
                params={"s": str(GRAVATAR_SIZE), "d": "404"},
                timeout=ClientTimeout(total=30),
            ) as resp:
                if resp.status == HTTPStatus.NOT_FOUND:
                    return None
                resp.raise_for_status()
                content = await resp.read()
        except (ClientError, TimeoutError) as err:
            raise CannotConnect from err
        if (content_type := sniff_content_type(content)) is None:
            raise CannotConnect
        return Avatar(content, content_type)


DATA_GRAVATAR: HassKey[GravatarManager] = HassKey(f"{DOMAIN}_gravatar")


class AvatarView(HomeAssistantView):
    """Serve avatars without auth, like core's /api/image/serve; see agents.md."""

    url = AVATAR_URL
    name = f"api:{DOMAIN}:avatar"
    requires_auth = False

    async def get(self, request: web.Request, user_id: str) -> web.Response:
        """Serve a user's avatar."""
        hass: HomeAssistant = request.app["hass"]
        manager = hass.data.get(DATA_GRAVATAR)
        if manager is None or (avatar := manager.avatar(user_id)) is None:
            raise web.HTTPNotFound
        return web.Response(
            body=avatar.content,
            content_type=avatar.content_type,
            # The URL changes whenever the image does, so it can be cached for long.
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )


async def _async_set_picture(
    hass: HomeAssistant, person: dict[str, Any], picture: str | None
) -> None:
    if person.get(_PICTURE) == picture:
        return
    await person_collection(hass).async_update_item(
        person["id"],
        # The update schema resets device trackers when they are not passed along.
        {_PICTURE: picture, _DEVICE_TRACKERS: person[_DEVICE_TRACKERS]},
    )


def _read_file(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)
