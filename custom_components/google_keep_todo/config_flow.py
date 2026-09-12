"""Config flow for Google Keep Todo Sync.

Auth is OAuth2 via Home Assistant's `application_credentials` platform: the
user registers their own Google Cloud OAuth client (Keep has no first-party
HA app to piggyback on), then authorizes it for their own account. See
application_credentials.py and the README for the one-time Google Cloud
Console setup this requires.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow, selector
import voluptuous as vol

from .const import (
    CONF_LIST_TITLES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    OAUTH2_SCOPES,
    USERINFO_URL,
)

_LOGGER = logging.getLogger(__name__)


def _parse_titles(raw: str) -> list[str]:
    # Order-preserving de-dupe, since a duplicated title would otherwise
    # collide on the same Keep note (see coordinator.py's by_title mapping).
    seen: dict[str, None] = {}
    for title in raw.split(","):
        title = title.strip()
        if title:
            seen.setdefault(title, None)
    return list(seen)


def _titles_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_LIST_TITLES, default=default): str})


class GoogleKeepConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle a config flow for Google Keep Todo Sync."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        super().__init__()
        self._oauth_data: dict[str, Any] | None = None
        self._email: str | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return the logger for this flow."""
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Request the Keep scope, a refresh token, and force the consent screen.

        `prompt=consent` guarantees a refresh_token even on a repeat
        authorization - Google otherwise omits it silently, which would
        leave this integration with only a short-lived access token.
        """
        return {
            "scope": " ".join(OAUTH2_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Look up the account's email, then move on to picking lists."""
        try:
            resp = await config_entry_oauth2_flow.async_oauth2_request(
                self.hass, data["token"], "GET", USERINFO_URL
            )
            resp.raise_for_status()
            userinfo = await resp.json()
        except ClientError:
            self.logger.exception("Failed to fetch Google account info")
            return self.async_abort(reason="cannot_connect")

        email = userinfo.get("email")
        if not email:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(email)
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch()
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(reauth_entry, data=data)

        self._abort_if_unique_id_configured()
        self._oauth_data = data
        self._email = email
        return await self.async_step_lists()

    async def async_step_lists(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask which Keep lists (by title) to sync."""
        errors: dict[str, str] = {}
        if user_input is not None:
            titles = _parse_titles(user_input[CONF_LIST_TITLES])
            if not titles:
                errors["base"] = "no_lists_selected"
            else:
                assert self._oauth_data is not None
                assert self._email is not None
                return self.async_create_entry(
                    title=self._email,
                    data=self._oauth_data,
                    options={
                        CONF_LIST_TITLES: titles,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        return self.async_show_form(step_id="lists", data_schema=_titles_schema(""), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return GoogleKeepOptionsFlow()


class GoogleKeepOptionsFlow(OptionsFlow):
    """Let the user change which list titles are synced, or the poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Edit the synced list titles and poll interval."""
        errors: dict[str, str] = {}
        current_titles = self.config_entry.options.get(CONF_LIST_TITLES, [])
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        if user_input is not None:
            titles = _parse_titles(user_input[CONF_LIST_TITLES])
            if not titles:
                errors["base"] = "no_lists_selected"
            else:
                return self.async_create_entry(
                    data={
                        CONF_LIST_TITLES: titles,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    }
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_LIST_TITLES, default=", ".join(current_titles)): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_scan_interval
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=3600,
                        step=10,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
