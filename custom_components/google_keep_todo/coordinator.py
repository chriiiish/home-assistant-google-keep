"""DataUpdateCoordinator for Google Keep Todo Sync."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging

from gkeepapi.node import List as KeepList
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GoogleKeepApi, GoogleKeepAuthError
from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class GoogleKeepUpdateCoordinator(DataUpdateCoordinator[dict[str, KeepList]]):
    """Owns the gkeepapi session for one config entry and exposes selected lists.

    All writes (todo entity mutations) and the periodic poll funnel through
    this coordinator so a single `Keep` instance is never touched from two
    threads at once, and every write is followed by `keep.sync()`, which is
    what actually pushes local changes up to Google and pulls down anything
    that changed remotely - the two-way sync happens inside `sync()` itself.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: GoogleKeepApi,
        list_ids: list[str],
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.entry = entry
        self.api = api
        self.list_ids = list_ids
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")

    async def async_setup(self) -> None:
        """Authenticate, resuming from cached state if we have any."""
        cached_state = await self._store.async_load()

        def _connect() -> None:
            self.api.authenticate(state=cached_state)

        try:
            await self.hass.async_add_executor_job(_connect)
        except GoogleKeepAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err

        await self._async_save_state()

    async def _async_update_data(self) -> dict[str, KeepList]:
        def _sync_and_read() -> dict[str, KeepList]:
            self.api.sync()
            data: dict[str, KeepList] = {}
            for list_id in self.list_ids:
                keep_list = self.api.get_list(list_id)
                if keep_list is not None:
                    data[list_id] = keep_list
                else:
                    _LOGGER.warning(
                        "Google Keep list %s is no longer available "
                        "(deleted, trashed, or unshared)",
                        list_id,
                    )
            return data

        try:
            data = await self.hass.async_add_executor_job(_sync_and_read)
        except GoogleKeepAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except Exception as err:  # noqa: BLE001 - surface any gkeepapi error to HA
            raise UpdateFailed(f"Error communicating with Google Keep: {err}") from err

        await self._async_save_state()
        return data

    async def _async_save_state(self) -> None:
        state = await self.hass.async_add_executor_job(self.api.dump)
        await self._store.async_save(state)

    async def async_execute(self, mutation: Callable[[], None]) -> None:
        """Run a blocking local mutation, then sync it up and refresh entities.

        `mutation` should only touch already-loaded gkeepapi node objects
        (e.g. `keep_list.add(...)`, `item.checked = True`, `item.delete()`).
        It marks the nodes dirty locally; the following sync pushes them to
        Google and pulls down anything that changed remotely in the meantime.
        """
        await self.hass.async_add_executor_job(mutation)
        await self.async_request_refresh()
