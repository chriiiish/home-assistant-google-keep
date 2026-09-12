"""application_credentials platform for Google Keep Todo Sync.

Google Keep has no first-party OAuth app you can piggyback on (unlike, say,
Google Tasks), so every user registers their own OAuth client in Google
Cloud Console and enters its client ID/secret under
Settings -> Application Credentials before adding this integration.
"""

from __future__ import annotations

from homeassistant.components.application_credentials import AuthorizationServer
from homeassistant.core import HomeAssistant

from .const import OAUTH2_AUTHORIZE, OAUTH2_TOKEN


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return the Google OAuth2 authorization server."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders shown on the credentials setup dialog."""
    return {
        "keep_api_url": "https://console.cloud.google.com/apis/library/keep.googleapis.com",
        "oauth_consent_url": "https://console.cloud.google.com/apis/credentials/consent",
        "oauth_creds_url": "https://console.cloud.google.com/apis/credentials",
    }
