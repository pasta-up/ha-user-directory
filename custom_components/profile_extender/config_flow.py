"""Config and options flows for Profile Extender."""

from __future__ import annotations

from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
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
    CONF_OIDC_ENABLED,
    CONF_OIDC_ENFORCE,
    CONF_OIDC_PROVIDER,
    DOMAIN,
    PANEL_TITLE,
)
from .oidc import AuthentikSync, OidcError, active_providers


class ProfileExtenderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add Profile Extender. SSO is set up afterwards under Configure."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        if user_input is not None:
            return self.async_create_entry(title=PANEL_TITLE, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> ProfileExtenderOptionsFlow:
        """Create the options flow."""
        return ProfileExtenderOptionsFlow()


class ProfileExtenderOptionsFlow(OptionsFlowWithReload):
    """Turn SSO contact sync on or off. Options flows are admin-only."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage SSO settings."""
        providers = active_providers(self.hass)
        current = self.config_entry.options
        errors: dict[str, str] = {}

        if user_input is not None:
            # A blank token keeps the saved one, so admins needn't re-enter it.
            token = user_input.get(CONF_AUTHENTIK_TOKEN) or current.get(
                CONF_AUTHENTIK_TOKEN
            )
            options = {**user_input, CONF_AUTHENTIK_TOKEN: token}
            if not user_input[CONF_OIDC_ENABLED]:
                return self.async_create_entry(
                    data={CONF_OIDC_ENABLED: False, CONF_OIDC_ENFORCE: False}
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
                    return self.async_create_entry(data=options)

        schema: dict[Any, Any] = {
            probatio.Required(CONF_OIDC_ENABLED, default=False): BooleanSelector()
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

        suggested = {
            k: v
            for k, v in (user_input or current).items()
            if k != CONF_AUTHENTIK_TOKEN
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema), suggested
            ),
            errors=errors,
            description_placeholders={
                "status": "detected" if providers else "not detected",
                "token_saved": "yes" if current.get(CONF_AUTHENTIK_TOKEN) else "no",
            },
        )
