"""Email verification by emailed code. See agents.md "Email verification"."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hmac
import logging
import secrets
from time import monotonic

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from .const import (
    CODE_MAX_ATTEMPTS,
    CODE_MAX_PER_HOUR,
    CODE_RESEND_AFTER,
    CODE_TTL,
    CONF_EMAIL,
    DOMAIN,
    STORAGE_KEY_VERIFIED,
    STORAGE_VERSION,
)
from .mail import Mailer, MailError
from .store import ContactStore

_LOGGER = logging.getLogger(__name__)

_HOUR = 3600.0


class VerifyError(Exception):
    """Verification failed; the message is the WebSocket error code."""


@dataclass(slots=True)
class _Pending:
    email: str
    code: str
    expires: float
    attempts: int = 0


class EmailVerifier:
    """Sends codes and remembers which address each user proved they own."""

    def __init__(self, hass: HomeAssistant, mailer: Mailer | None) -> None:
        """Create the verifier; call async_load before use."""
        self._hass = hass
        self._mailer = mailer
        # {user_id: verified email, casefolded}
        self._store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_VERIFIED, private=True
        )
        self._verified: dict[str, str] = {}
        # Codes live in memory only; a restart just means asking for a new one.
        self._pending: dict[str, _Pending] = {}
        self._sent: dict[str, list[float]] = {}

    async def async_load(self) -> None:
        """Load verified addresses."""
        self._verified = await self._store.async_load() or {}

    @property
    def available(self) -> bool:
        """Return whether an admin has set up email."""
        return self._mailer is not None

    def is_verified(self, user_id: str, email: str) -> bool:
        """Return whether the user proved they own this address."""
        return self._verified.get(user_id) == email.casefold()

    def pending(self, user_id: str, email: str) -> bool:
        """Return whether a code for this address is waiting to be entered."""
        pending = self._pending.get(user_id)
        return (
            pending is not None
            and pending.email == email.casefold()
            and pending.expires > monotonic()
        )

    async def async_send_code(self, user_id: str, email: str) -> None:
        """Email a new code. Raises VerifyError."""
        if self._mailer is None:
            raise VerifyError("not_configured")
        if self.is_verified(user_id, email):
            raise VerifyError("already_verified")
        now = monotonic()
        sent = [t for t in self._sent.get(user_id, []) if now - t < _HOUR]
        # The cooldown is per address, so fixing a typo needn't wait; the hourly cap still applies.
        last = self._pending.get(user_id)
        if (
            last is not None
            and last.email == email.casefold()
            and now - sent[-1] < CODE_RESEND_AFTER.total_seconds()
        ):
            raise VerifyError("too_soon")
        if len(sent) >= CODE_MAX_PER_HOUR:
            raise VerifyError("too_many_codes")

        code = f"{secrets.randbelow(1_000_000):06d}"
        minutes = int(CODE_TTL.total_seconds() // 60)
        try:
            await self._mailer.async_send(
                email,
                f"Your verification code: {code}",
                f"Your code to verify this email on {self._hass.config.location_name}"
                f" is {code}.\n\nIt expires in {minutes} minutes. If you didn't ask"
                " for it, you can ignore this email.\n",
            )
        except MailError as err:
            _LOGGER.warning("Couldn't send a verification email: %s", err.__cause__)
            raise VerifyError("send_failed") from err
        self._sent[user_id] = [*sent, now]
        self._pending[user_id] = _Pending(
            email.casefold(), code, now + CODE_TTL.total_seconds()
        )

    async def async_confirm(self, user_id: str, email: str, code: str) -> None:
        """Mark the address verified if the code is right. Raises VerifyError."""
        if not self.pending(user_id, email):
            self._pending.pop(user_id, None)
            raise VerifyError("no_code")
        pending = self._pending[user_id]
        pending.attempts += 1
        if not hmac.compare_digest(pending.code, code.strip()):
            if pending.attempts >= CODE_MAX_ATTEMPTS:
                del self._pending[user_id]
                raise VerifyError("too_many_attempts")
            raise VerifyError("wrong_code")
        del self._pending[user_id]
        self._verified[user_id] = pending.email
        await self._store.async_save(self._verified)

    async def async_remove_user(self, user_id: str) -> None:
        """Forget a user."""
        self._pending.pop(user_id, None)
        self._sent.pop(user_id, None)
        if self._verified.pop(user_id, None) is not None:
            await self._store.async_save(self._verified)

    async def async_remove(self) -> None:
        """Delete the storage file."""
        self._verified = {}
        await self._store.async_remove()


def verified_email(
    store: ContactStore, verifier: EmailVerifier, user_id: str
) -> str | None:
    """Return the user's email if verified. SSO emails count; the IdP vouches for them."""
    email = store.get(user_id).get(CONF_EMAIL)
    if not email:
        return None
    if store.oidc(user_id).get(CONF_EMAIL) == email or verifier.is_verified(
        user_id, email
    ):
        return email
    return None


def verified_email_getter(
    store: ContactStore, verifier: EmailVerifier
) -> Callable[[str], str | None]:
    """Return verified_email bound to the store and verifier, for Gravatar refreshes."""
    return lambda user_id: verified_email(store, verifier, user_id)


DATA_VERIFIER: HassKey[EmailVerifier] = HassKey(f"{DOMAIN}_verifier")
