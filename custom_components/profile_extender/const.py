"""Constants for Profile Extender."""

from typing import Final

DOMAIN: Final = "profile_extender"

CONF_EMAIL: Final = "email"
CONF_PHONE: Final = "phone"
CONF_GITHUB: Final = "github"
CONTACT_FIELDS: Final = (CONF_EMAIL, CONF_PHONE, CONF_GITHUB)

STORAGE_KEY: Final = f"{DOMAIN}.contacts"
STORAGE_VERSION: Final = 1

PANEL_URL_PATH: Final = "contact-info"
PANEL_COMPONENT: Final = "profile-extender-panel"
PANEL_ICON: Final = "mdi:card-account-details"
PANEL_TITLE: Final = "Contact info"
STATIC_URL: Final = f"/{DOMAIN}_static"
