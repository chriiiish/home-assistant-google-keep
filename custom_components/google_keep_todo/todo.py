"""Todo platform for Google Keep Todo Sync.

Each selected Google Keep list is exposed as one Home Assistant `todo` list
entity. Google Keep supports one level of sub-item nesting that the HA
`todo` platform has no equivalent for, so nested checklist items are not
shown here and are left untouched on the Keep side.
"""

from __future__ import annotations

import logging

from gkeepapi.node import (
    List as KeepList,
    ListItem as KeepListItem,
    NewListItemPlacementValue,
)
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Keep todo list entities for a config entry."""
    coordinator: GoogleKeepUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoogleKeepTodoListEntity(coordinator, list_id) for list_id in coordinator.list_ids
    )


class GoogleKeepTodoListEntity(CoordinatorEntity[GoogleKeepUpdateCoordinator], TodoListEntity):
    """A Home Assistant todo list backed by a Google Keep list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
    )

    def __init__(self, coordinator: GoogleKeepUpdateCoordinator, list_id: str) -> None:
        """Initialize the entity for a single Keep list id."""
        super().__init__(coordinator)
        self._list_id = list_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{list_id}"

    @property
    def _keep_list(self) -> KeepList | None:
        return self.coordinator.data.get(self._list_id) if self.coordinator.data else None

    @property
    def name(self) -> str:
        """Return the current Keep list title."""
        keep_list = self._keep_list
        return keep_list.title if keep_list is not None else "Google Keep list"

    @property
    def available(self) -> bool:
        """Entity is unavailable if the list was deleted/unshared remotely."""
        return super().available and self._keep_list is not None

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return top-level (non-indented) items in Keep's display order."""
        keep_list = self._keep_list
        if keep_list is None:
            return None
        return [
            TodoItem(
                uid=item.id,
                summary=item.text,
                status=(TodoItemStatus.COMPLETED if item.checked else TodoItemStatus.NEEDS_ACTION),
            )
            for item in keep_list.items
            if not item.indented
        ]

    def _top_level_items(self, keep_list: KeepList) -> list[KeepListItem]:
        return [item for item in keep_list.items if not item.indented]

    def _find_item(self, uid: str) -> KeepListItem | None:
        keep_list = self._keep_list
        if keep_list is None:
            return None
        for item in self._top_level_items(keep_list):
            if item.id == uid:
                return item
        return None

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new item on the Keep list."""

        def _create() -> None:
            keep_list = self._keep_list
            if keep_list is None:
                raise HomeAssistantError("Google Keep list is not available")
            keep_list.add(
                item.summary or "",
                checked=item.status == TodoItemStatus.COMPLETED,
                sort=NewListItemPlacementValue.Bottom,
            )

        await self.coordinator.async_execute(_create)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an existing item's text and/or completion state."""

        def _update() -> None:
            keep_item = self._find_item(item.uid)
            if keep_item is None:
                raise HomeAssistantError(f"Todo item {item.uid} not found")
            if item.summary is not None:
                keep_item.text = item.summary
            if item.status is not None:
                keep_item.checked = item.status == TodoItemStatus.COMPLETED

        await self.coordinator.async_execute(_update)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more items from the Keep list."""

        def _delete() -> None:
            for uid in uids:
                keep_item = self._find_item(uid)
                if keep_item is not None:
                    keep_item.delete()

        await self.coordinator.async_execute(_delete)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        """Reorder an item to sit immediately after `previous_uid` (or first)."""

        def _move() -> None:
            keep_list = self._keep_list
            if keep_list is None:
                raise HomeAssistantError("Google Keep list is not available")

            items = self._top_level_items(keep_list)
            moving = next((i for i in items if i.id == uid), None)
            if moving is None:
                raise HomeAssistantError(f"Todo item {uid} not found")

            remaining = [i for i in items if i.id != uid]
            index = 0
            if previous_uid is not None:
                prev_index = next(
                    (idx for idx, i in enumerate(remaining) if i.id == previous_uid),
                    None,
                )
                if prev_index is None:
                    raise HomeAssistantError(f"Todo item {previous_uid} not found")
                index = prev_index + 1

            # `items` is sorted highest-sort-first (Keep's display order), so
            # the item before the target position has the higher sort value.
            prev_item = remaining[index - 1] if index > 0 else None
            next_item = remaining[index] if index < len(remaining) else None

            if prev_item is not None and next_item is not None:
                moving.sort = (prev_item.sort + next_item.sort) // 2
            elif prev_item is not None:
                moving.sort = prev_item.sort - KeepList.SORT_DELTA
            elif next_item is not None:
                moving.sort = next_item.sort + KeepList.SORT_DELTA

        await self.coordinator.async_execute(_move)
