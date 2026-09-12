"""Thin synchronous wrapper around gkeepapi.

Google's own Keep API only grants its OAuth scopes to Google Workspace
accounts, not personal @gmail.com accounts (confirmed by
`invalid_scope` errors when the scope isn't even selectable on a personal
project's OAuth consent screen). For a personal account, gkeepapi - an
unofficial client authenticated with a Google master token - is the only
option. It's entirely blocking (it uses `requests` under the hood), so
every public method on GoogleKeepApi is blocking too. Callers (the
coordinator and todo entities) are responsible for running these through
`hass.async_add_executor_job`; nothing in this module may be awaited
directly.
"""

from __future__ import annotations

import logging

import gkeepapi
from gkeepapi.exception import LoginException
from gkeepapi.node import List as KeepList

_LOGGER = logging.getLogger(__name__)


class GoogleKeepAuthError(Exception):
    """Raised when authentication with Google Keep fails."""


class GoogleKeepApi:
    """Blocking wrapper around a single gkeepapi.Keep session."""

    def __init__(self, email: str, master_token: str, device_id: str) -> None:
        self._email = email
        self._master_token = master_token
        self._device_id = device_id
        self.keep = gkeepapi.Keep()

    def authenticate(self, state: dict | None = None) -> None:
        """Authenticate using the stored master token, optionally resuming from cached state."""
        try:
            self.keep.authenticate(
                self._email,
                self._master_token,
                state=state,
                device_id=self._device_id,
            )
        except LoginException as err:
            raise GoogleKeepAuthError(str(err)) from err

    def sync(self) -> None:
        """Push local changes and pull remote changes."""
        try:
            self.keep.sync()
        except gkeepapi.exception.ResyncRequiredException:
            _LOGGER.warning("Google Keep requested a full resync")
            self.keep.sync(resync=True)

    def dump(self) -> dict:
        """Serialize local Keep state so a restart doesn't require a full resync."""
        return self.keep.dump()

    def get_lists(self) -> list[KeepList]:
        """Return all non-trashed, non-archived Keep lists known locally."""
        return [
            node
            for node in self.keep.all()
            if isinstance(node, KeepList) and not node.trashed and not node.archived
        ]

    def get_list(self, list_id: str) -> KeepList | None:
        """Look up a single Keep list by id."""
        node = self.keep.get(list_id)
        if isinstance(node, KeepList) and not node.trashed:
            return node
        return None

    def create_list(self, title: str) -> KeepList:
        """Create a new Keep list."""
        return self.keep.createList(title)
