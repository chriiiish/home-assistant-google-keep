"""Todo platform for Google Keep Todo Sync.

The Google Keep REST API has no per-item id and no update/patch method, so
every mutation is expressed as "the full new list of item texts" and pushed
via `coordinator.async_replace_items`, which recreates the whole note (see
coordinator.py). Two consequences of that, both accepted trade-offs for
using the official API instead of an unofficial master-token client:

- Checking an item off is treated as deleting it - there's nowhere to
  durably store "checked" state across a create+delete cycle other than
  dropping the item, which also matches how a disposable checklist is
  normally used.
- Items have no server-assigned id, so a uid is derived from the item text
  itself. Two items with identical text in the same list are indistinguishable
  and will collide - keep item text unique within a list.
"""

from __future__ import annotations

import hashlib
import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GoogleKeepUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _uid_for_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]  # noqa: S324 - identity, not security


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Keep todo list entities for a config entry."""
    coordinator: GoogleKeepUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoogleKeepTodoListEntity(coordinator, title) for title in coordinator.list_titles
    )


class GoogleKeepTodoListEntity(CoordinatorEntity[GoogleKeepUpdateCoordinator], TodoListEntity):
    """A Home Assistant todo list backed by a Google Keep checklist note."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
    )

    def __init__(self, coordinator: GoogleKeepUpdateCoordinator, title: str) -> None:
        """Initialize the entity for a single Keep list title."""
        super().__init__(coordinator)
        self._title = title
        self._attr_name = title
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{title}"

    @property
    def _texts(self) -> list[str]:
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get(self._title, [])

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return active items. Checked items don't exist here - see module docstring."""
        return [
            TodoItem(
                uid=_uid_for_text(text),
                summary=text,
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for text in self._texts
        ]

    def _index_for_uid(self, texts: list[str], uid: str) -> int | None:
        for index, text in enumerate(texts):
            if _uid_for_text(text) == uid:
                return index
        return None

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a new item to the bottom of the list."""
        texts = [*self._texts, item.summary or ""]
        await self.coordinator.async_replace_items(self._title, texts)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Rename an item, or remove it if it was marked completed."""
        texts = list(self._texts)
        index = self._index_for_uid(texts, item.uid)
        if index is None:
            raise HomeAssistantError(f"Todo item {item.uid} not found")

        if item.status == TodoItemStatus.COMPLETED:
            texts.pop(index)
        elif item.summary is not None:
            texts[index] = item.summary

        await self.coordinator.async_replace_items(self._title, texts)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more items from the list."""
        texts = list(self._texts)
        remove_indexes = set()
        for uid in uids:
            index = self._index_for_uid(texts, uid)
            if index is not None:
                remove_indexes.add(index)
        texts = [text for i, text in enumerate(texts) if i not in remove_indexes]
        await self.coordinator.async_replace_items(self._title, texts)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        """Reorder an item to sit immediately after `previous_uid` (or first)."""
        texts = list(self._texts)
        index = self._index_for_uid(texts, uid)
        if index is None:
            raise HomeAssistantError(f"Todo item {uid} not found")
        text = texts.pop(index)

        if previous_uid is None:
            texts.insert(0, text)
        else:
            prev_index = self._index_for_uid(texts, previous_uid)
            if prev_index is None:
                raise HomeAssistantError(f"Todo item {previous_uid} not found")
            texts.insert(prev_index + 1, text)

        await self.coordinator.async_replace_items(self._title, texts)
