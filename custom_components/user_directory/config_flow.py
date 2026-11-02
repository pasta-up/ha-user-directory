"""Config and options flows for ha-user-directory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.http import current_request
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_AUTHENTIK_TOKEN,
    CONF_EMAIL,
    CONF_OIDC_ENABLED,
    CONF_OIDC_ENFORCE,
    CONF_OIDC_PROVIDER,
    CONF_PUBLISH_POLICY,
    CONF_SMTP_HOST,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_PORT,
    CONF_SMTP_SECURITY,
    CONF_SMTP_SENDER,
    CONF_SMTP_USERNAME,
    DOMAIN,
    INTEGRATION_TITLE,
    POLICIES,
    POLICY_CHOICE,
    SECURITY_STARTTLS,
    SMTP_OPTIONS,
    SMTP_PORTS,
)
from .mail import Mailer, MailError, SmtpConfig
from .oidc import AuthentikSync, OidcError, active_providers
from .store import InvalidContact, clean_contact
from .websocket import DATA_STORE

CONF_TEST_RECIPIENT = "test_recipient"


class UserDirectoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add ha-user-directory. SSO is set up afterwards under Configure."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        if user_input is not None:
            return self.async_create_entry(title=INTEGRATION_TITLE, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> UserDirectoryOptionsFlow:
        """Create the options flow."""
        return UserDirectoryOptionsFlow()


class UserDirectoryOptionsFlow(OptionsFlowWithReload):
    """Directory policy, SSO and email settings. Options flows are admin-only."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which settings to change."""
        menu = ["directory", "sso", "email"]
        if SmtpConfig.from_options(self.config_entry.options):
            menu.append("email_test")
        return self.async_show_menu(step_id="init", menu_options=menu)

    def _save(
        self, changes: dict[str, Any], drop: tuple[str, ...] = ()
    ) -> ConfigFlowResult:
        """Save changes on top of the other steps' options."""
        options = {k: v for k, v in self.config_entry.options.items() if k not in drop}
        return self.async_create_entry(data={**options, **changes})

    async def async_step_directory(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose who is listed."""
        if user_input is not None:
            return self._save(user_input)
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_PUBLISH_POLICY, default=POLICY_CHOICE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(POLICIES),
                        mode=SelectSelectorMode.LIST,
                        translation_key=CONF_PUBLISH_POLICY,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="directory",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )

    async def async_step_sso(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage SSO contact sync."""
        providers = active_providers(self.hass)
        current = self.config_entry.options
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input[CONF_OIDC_ENABLED]:
                return self._save(
                    {CONF_OIDC_ENABLED: False, CONF_OIDC_ENFORCE: False},
                    drop=(CONF_OIDC_PROVIDER, CONF_AUTHENTIK_TOKEN),
                )
            # A blank token keeps the saved one, so admins needn't re-enter it.
            token = user_input.get(CONF_AUTHENTIK_TOKEN) or current.get(
                CONF_AUTHENTIK_TOKEN
            )
            if not providers:
                errors["base"] = "provider_not_active"
            elif not token:
                errors[CONF_AUTHENTIK_TOKEN] = "token_required"
            else:
                try:
                    await AuthentikSync(self.hass, token).async_connect()
                except OidcError as err:
                    errors["base"] = str(err)
                else:
                    return self._save({**user_input, CONF_AUTHENTIK_TOKEN: token})

        schema: dict[Any, Any] = {
            probatio.Required(CONF_OIDC_ENABLED, default=False): BooleanSelector(),
        }
        if providers:
            schema[
                probatio.Required(CONF_OIDC_PROVIDER, default=next(iter(providers)))
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=key, label=label)
                        for key, label in providers.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            schema[probatio.Optional(CONF_AUTHENTIK_TOKEN)] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            )
            schema[probatio.Required(CONF_OIDC_ENFORCE, default=False)] = (
                BooleanSelector()
            )

        return self.async_show_form(
            step_id="sso",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema),
                _without(user_input or current, CONF_AUTHENTIK_TOKEN),
            ),
            errors=errors,
            description_placeholders={
                "status": "detected" if providers else "not detected",
                "token_saved": "yes" if current.get(CONF_AUTHENTIK_TOKEN) else "no",
            },
        )

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up the SMTP server that sends verification codes."""
        current = self.config_entry.options
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_SMTP_HOST):
                return self._save({}, drop=SMTP_OPTIONS)
            smtp = {k: v for k, v in user_input.items() if v not in (None, "")}
            if CONF_SMTP_PORT in smtp:
                smtp[CONF_SMTP_PORT] = int(smtp[CONF_SMTP_PORT])
            # A blank password keeps the saved one, like the SSO token.
            if CONF_SMTP_PASSWORD not in smtp and current.get(CONF_SMTP_PASSWORD):
                smtp[CONF_SMTP_PASSWORD] = current[CONF_SMTP_PASSWORD]
            if not smtp.get(CONF_SMTP_USERNAME):
                smtp.pop(CONF_SMTP_PASSWORD, None)
            try:
                valid = bool(clean_contact({CONF_EMAIL: smtp.get(CONF_SMTP_SENDER)}))
            except InvalidContact:
                valid = False
            if not valid:
                errors[CONF_SMTP_SENDER] = "invalid_email"
            else:
                config = SmtpConfig.from_options(smtp)
                assert config is not None
                try:
                    await Mailer(self.hass, config).async_test()
                except MailError as err:
                    errors["base"] = str(err)
                else:
                    return self._save(smtp, drop=SMTP_OPTIONS)

        schema = probatio.Schema(
            {
                probatio.Optional(CONF_SMTP_HOST): TextSelector(),
                probatio.Required(
                    CONF_SMTP_SECURITY, default=SECURITY_STARTTLS
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(SMTP_PORTS),
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key=CONF_SMTP_SECURITY,
                    )
                ),
                probatio.Optional(CONF_SMTP_PORT): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=65535, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                probatio.Optional(CONF_SMTP_USERNAME): TextSelector(),
                probatio.Optional(CONF_SMTP_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                probatio.Optional(CONF_SMTP_SENDER): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
            }
        )
        return self.async_show_form(
            step_id="email",
            data_schema=self.add_suggested_values_to_schema(
                schema, _without(user_input or current, CONF_SMTP_PASSWORD)
            ),
            errors=errors,
            description_placeholders={
                "password_saved": "yes" if current.get(CONF_SMTP_PASSWORD) else "no",
            },
        )

    async def async_step_email_test(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Send a test email with the saved SMTP settings."""
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            to = user_input.get(CONF_TEST_RECIPIENT, "")
            try:
                valid = bool(clean_contact({CONF_EMAIL: to}))
            except InvalidContact:
                valid = False
            if not valid:
                errors[CONF_TEST_RECIPIENT] = "invalid_email"
            else:
                config = SmtpConfig.from_options(self.config_entry.options)
                assert config is not None
                try:
                    await Mailer(self.hass, config).async_send(
                        to,
                        "Test email from Home Assistant",
                        "ha-user-directory can send email. Verification codes"
                        " will come from this address.\n",
                    )
                except MailError as err:
                    errors["base"] = str(err)
                    # Admins only, so the server's own message is safe to show.
                    detail = f"\n\nServer said: {err.__cause__}"
                else:
                    return self.async_abort(
                        reason="test_sent", description_placeholders={"email": to}
                    )

        schema = probatio.Schema(
            {
                probatio.Required(CONF_TEST_RECIPIENT): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
            }
        )
        return self.async_show_form(
            step_id="email_test",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {CONF_TEST_RECIPIENT: self._admin_email()}
            ),
            errors=errors,
            description_placeholders={"detail": detail},
        )

    def _admin_email(self) -> str:
        """Return the email of the admin using this dialog, if they've set one."""
        # Options flows don't record who opened them; core's Plex flow reads the request too.
        request = current_request.get()
        store = self.hass.data.get(DATA_STORE)
        if request is None or store is None:
            return ""
        return store.get(request["hass_user"].id).get(CONF_EMAIL, "")


def _without(values: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in values.items() if k != key}
