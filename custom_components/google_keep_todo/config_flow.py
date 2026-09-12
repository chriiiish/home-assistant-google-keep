"""Config flow for Google Keep Todo Sync."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from . import generate_device_id
from .api import GoogleKeepApi, GoogleKeepAuthError
from .const import (
    CONF_DEVICE_ID,
    CONF_LIST_IDS,
    CONF_MASTER_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_MASTER_TOKEN): str,
    }
)


def _list_selector_options(keep_lists) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=keep_list.id, label=keep_list.title or "(untitled list)")
        for keep_list in keep_lists
    ]


def _list_ids_schema(options: list[selector.SelectOptionDict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LIST_IDS): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


class GoogleKeepConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Google Keep Todo Sync."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._email: str | None = None
        self._master_token: str | None = None
        self._device_id: str | None = None
        self._api: GoogleKeepApi | None = None
        self._list_options: list[selector.SelectOptionDict] = []
        self._reauth_entry: ConfigEntry | None = None

    async def _async_validate_and_sync(
        self, email: str, master_token: str, device_id: str
    ) -> GoogleKeepApi:
        """Authenticate and do an initial sync; raises GoogleKeepAuthError on failure."""
        api = GoogleKeepApi(email=email, master_token=master_token, device_id=device_id)

        def _connect() -> None:
            api.authenticate()

        await self.hass.async_add_executor_job(_connect)
        return api

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect the account email and master token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            master_token = user_input[CONF_MASTER_TOKEN]

            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()

            device_id = generate_device_id()
            try:
                api = await self._async_validate_and_sync(email, master_token, device_id)
            except GoogleKeepAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Google Keep credentials")
                errors["base"] = "unknown"
            else:
                self._email = email
                self._master_token = master_token
                self._device_id = device_id
                self._api = api
                self._list_options = _list_selector_options(api.get_lists())
                if not self._list_options:
                    errors["base"] = "no_lists"
                else:
                    return await self.async_step_lists()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_lists(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Let the user choose which Keep lists to sync."""
        errors: dict[str, str] = {}
        if user_input is not None:
            list_ids = user_input[CONF_LIST_IDS]
            if not list_ids:
                errors["base"] = "no_lists_selected"
            else:
                assert self._email is not None
                assert self._master_token is not None
                assert self._device_id is not None

                if self._reauth_entry is not None:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data={
                            CONF_EMAIL: self._email,
                            CONF_MASTER_TOKEN: self._master_token,
                            CONF_DEVICE_ID: self._device_id,
                        },
                    )

                return self.async_create_entry(
                    title=self._email,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_MASTER_TOKEN: self._master_token,
                        CONF_DEVICE_ID: self._device_id,
                    },
                    options={CONF_LIST_IDS: list_ids},
                )

        return self.async_show_form(
            step_id="lists",
            data_schema=_list_ids_schema(self._list_options),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when the master token stops working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._email = entry_data[CONF_EMAIL]
        self._device_id = entry_data[CONF_DEVICE_ID]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh master token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._email is not None
            assert self._device_id is not None
            master_token = user_input[CONF_MASTER_TOKEN]
            try:
                api = await self._async_validate_and_sync(
                    self._email, master_token, self._device_id
                )
            except GoogleKeepAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Google Keep credentials")
                errors["base"] = "unknown"
            else:
                self._master_token = master_token
                self._api = api
                assert self._reauth_entry is not None
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={
                        CONF_EMAIL: self._email,
                        CONF_MASTER_TOKEN: master_token,
                        CONF_DEVICE_ID: self._device_id,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_MASTER_TOKEN): str}),
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return GoogleKeepOptionsFlow()


class GoogleKeepOptionsFlow(OptionsFlow):
    """Let the user change which lists are synced, or the poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Re-fetch the current list of Keep lists and let the user reselect."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        api = GoogleKeepApi(
            email=self.config_entry.data[CONF_EMAIL],
            master_token=self.config_entry.data[CONF_MASTER_TOKEN],
            device_id=self.config_entry.data[CONF_DEVICE_ID],
        )

        def _connect_and_list():
            api.authenticate()
            return api.get_lists()

        try:
            keep_lists = await self.hass.async_add_executor_job(_connect_and_list)
        except GoogleKeepAuthError:
            errors["base"] = "invalid_auth"
            keep_lists = []
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error fetching Google Keep lists")
            errors["base"] = "unknown"
            keep_lists = []

        options = _list_selector_options(keep_lists)
        current_list_ids = self.config_entry.options.get(CONF_LIST_IDS, [])
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_LIST_IDS, default=current_list_ids): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
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
