"""The Google Keep Todo Sync integration."""

from __future__ import annotations

import binascii
from datetime import timedelta
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, Platform
from homeassistant.core import HomeAssistant

from .api import GoogleKeepApi
from .const import (
    CONF_DEVICE_ID,
    CONF_LIST_IDS,
    CONF_MASTER_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import GoogleKeepUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.TODO]


def generate_device_id() -> str:
    """Generate a stable, random Android-style device id for gkeepapi.

    This must stay the same across restarts once chosen - Google associates
    the master token with a device, so persist whatever this returns in the
    config entry rather than regenerating it on every setup.
    """
    return binascii.hexlify(os.urandom(8)).decode()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Google Keep Todo Sync from a config entry."""
    api = GoogleKeepApi(
        email=entry.data[CONF_EMAIL],
        master_token=entry.data[CONF_MASTER_TOKEN],
        device_id=entry.data[CONF_DEVICE_ID],
    )

    coordinator = GoogleKeepUpdateCoordinator(
        hass,
        entry,
        api,
        list_ids=entry.options.get(CONF_LIST_IDS, []),
        update_interval=timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
    )
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change, e.g. a different set of lists is selected."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
