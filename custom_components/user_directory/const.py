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

CONF_SMTP_HOST: Final = "smtp_host"
CONF_SMTP_PORT: Final = "smtp_port"
CONF_SMTP_SECURITY: Final = "smtp_security"
CONF_SMTP_USERNAME: Final = "smtp_username"
CONF_SMTP_PASSWORD: Final = "smtp_password"
CONF_SMTP_SENDER: Final = "smtp_sender"
SMTP_OPTIONS: Final = (
    CONF_SMTP_HOST,
    CONF_SMTP_PORT,
    CONF_SMTP_SECURITY,
    CONF_SMTP_USERNAME,
    CONF_SMTP_PASSWORD,
    CONF_SMTP_SENDER,
)
SECURITY_STARTTLS: Final = "starttls"
SECURITY_SSL: Final = "ssl"
SECURITY_NONE: Final = "none"
# Default port for each encryption mode.
SMTP_PORTS: Final = {SECURITY_STARTTLS: 587, SECURITY_SSL: 465, SECURITY_NONE: 25}

# Email verification codes; see agents.md "Email verification".
CODE_TTL: Final = timedelta(minutes=15)
CODE_RESEND_AFTER: Final = timedelta(minutes=1)
CODE_MAX_ATTEMPTS: Final = 5
CODE_MAX_PER_HOUR: Final = 5

GRAVATAR_URL: Final = "https://gravatar.com/avatar/{hash}"
GRAVATAR_SIZE: Final = 512
GRAVATAR_REFRESH_INTERVAL: Final = timedelta(hours=6)
AVATAR_URL: Final = f"/api/{DOMAIN}/avatar/{{user_id}}"

STORAGE_KEY: Final = f"{DOMAIN}.contacts"
STORAGE_KEY_OIDC: Final = f"{DOMAIN}.oidc"
STORAGE_KEY_GRAVATAR: Final = f"{DOMAIN}.gravatar"
STORAGE_KEY_SETTINGS: Final = f"{DOMAIN}.settings"
STORAGE_KEY_VERIFIED: Final = f"{DOMAIN}.verified"
STORAGE_VERSION: Final = 1

PANEL_URL_PATH: Final = "user-directory"
PANEL_COMPONENT: Final = "user-directory-panel"
PANEL_ICON: Final = "mdi:card-account-phone"
PANEL_TITLE: Final = "User-Directory"
STATIC_URL: Final = f"/{DOMAIN}_static"
