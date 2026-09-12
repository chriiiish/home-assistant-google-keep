"""DataUpdateCoordinator for Google Keep Todo Sync."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GoogleKeepApiError, GoogleKeepRestApi, is_list_note, top_level_item_texts
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class GoogleKeepUpdateCoordinator(DataUpdateCoordinator[dict[str, list[str]]]):
    """Polls Google Keep and serializes all writes for one config entry.

    Because the Keep API has no update/patch method, every local change
    (create, edit, complete, delete, or reorder an item) is applied as:
    build the full desired list of item texts -> create a brand-new note
    with that title and those items -> delete the old note. `list_titles`
    identifies each synced list by its Keep note title, since a note's id
    changes every time it's recreated.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: GoogleKeepRestApi,
        list_titles: list[str],
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
        self.list_titles = list_titles
        # title -> current note resource name (e.g. "notes/abc123")
        self._note_names: dict[str, str] = {}

    async def _async_update_data(self) -> dict[str, list[str]]:
        try:
            notes = await self.api.async_list_notes()
        except GoogleKeepApiError as err:
            raise UpdateFailed(f"Error communicating with Google Keep: {err}") from err

        by_title: dict[str, dict] = {}
        for note in notes:
            if not is_list_note(note):
                continue
            title = note.get("title", "")
            if title in by_title:
                _LOGGER.warning(
                    "Multiple Google Keep lists are titled %r; using the most "
                    "recently created one and ignoring the rest. Give your "
                    "lists unique titles to avoid this",
                    title,
                )
                if note["createTime"] <= by_title[title]["createTime"]:
                    continue
            by_title[title] = note

        data: dict[str, list[str]] = {}
        for title in self.list_titles:
            note = by_title.get(title)
            if note is None:
                # First run, or the note was deleted/renamed on the Keep side.
                try:
                    note = await self.api.async_create_list_note(title, [])
                except GoogleKeepApiError as err:
                    raise UpdateFailed(f"Error creating Google Keep list {title!r}: {err}") from err
            self._note_names[title] = note["name"]
            data[title] = top_level_item_texts(note)
        return data

    async def async_replace_items(self, title: str, item_texts: list[str]) -> None:
        """Replace all items in `title`'s list, then refresh entities."""
        old_name = self._note_names.get(title)
        try:
            new_note = await self.api.async_create_list_note(title, item_texts)
            self._note_names[title] = new_note["name"]
            if old_name is not None:
                await self.api.async_delete_note(old_name)
        except GoogleKeepApiError as err:
            raise HomeAssistantError(f"Error updating Google Keep list {title!r}: {err}") from err

        await self.async_request_refresh()
