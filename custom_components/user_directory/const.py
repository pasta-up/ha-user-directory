"""Constants for ha-user-directory."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "user_directory"
# Admin-facing name; users see PANEL_TITLE.
INTEGRATION_TITLE: Final = "ha-user-directory"

CONF_EMAIL: Final = "email"
CONF_PHONE: Final = "phone"
CONF_GITHUB: Final = "github"
CONTACT_FIELDS: Final = (CONF_EMAIL, CONF_PHONE, CONF_GITHUB)
# Shown in the directory only if the user opts in, field by field.
SOCIAL_FIELDS: Final = (CONF_GITHUB,)

CONF_PUBLISH_POLICY: Final = "publish_policy"
POLICY_CHOICE: Final = "choice"
POLICY_OIDC: Final = "oidc"
POLICY_ALL: Final = "all"
POLICIES: Final = (POLICY_CHOICE, POLICY_OIDC, POLICY_ALL)

CONF_OIDC_ENABLED: Final = "oidc_enabled"
CONF_OIDC_PROVIDER: Final = "oidc_provider"
CONF_OIDC_ENFORCE: Final = "oidc_enforce"
CONF_AUTHENTIK_TOKEN: Final = "authentik_token"

# Login integrations we can read SSO details from; see agents.md "SSO".
PROVIDER_AUTH_OIDC: Final = "auth_oidc"
SUPPORTED_PROVIDERS: Final = {PROVIDER_AUTH_OIDC: "OpenID Connect/SSO (hass-oidc-auth)"}

OIDC_SYNC_INTERVAL: Final = timedelta(hours=1)

GRAVATAR_URL: Final = "https://gravatar.com/avatar/{hash}"
GRAVATAR_SIZE: Final = 512
GRAVATAR_REFRESH_INTERVAL: Final = timedelta(hours=6)
AVATAR_URL: Final = f"/api/{DOMAIN}/avatar/{{user_id}}"

STORAGE_KEY: Final = f"{DOMAIN}.contacts"
STORAGE_KEY_OIDC: Final = f"{DOMAIN}.oidc"
STORAGE_KEY_GRAVATAR: Final = f"{DOMAIN}.gravatar"
STORAGE_KEY_SETTINGS: Final = f"{DOMAIN}.settings"
STORAGE_VERSION: Final = 1

PANEL_URL_PATH: Final = "user-directory"
PANEL_COMPONENT: Final = "user-directory-panel"
PANEL_ICON: Final = "mdi:card-account-phone"
PANEL_TITLE: Final = "User-Directory"
STATIC_URL: Final = f"/{DOMAIN}_static"
