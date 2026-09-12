"""Minimal async client for the official Google Keep REST API.

The API only exposes notes.create / notes.get / notes.list / notes.delete -
there is no update/patch method for a note or for individual list items.
Every local change is therefore implemented as "build the full desired item
list, create a new note with it, delete the old note" (see coordinator.py).
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import config_entry_oauth2_flow

from .const import API_BASE_URL, USERINFO_URL


class GoogleKeepApiError(Exception):
    """Raised when a Google Keep API call fails."""


class GoogleKeepRestApi:
    """Thin async wrapper around the Google Keep REST API."""

    def __init__(self, oauth_session: config_entry_oauth2_flow.OAuth2Session) -> None:
        self._session = oauth_session

    async def async_get_email(self) -> str:
        """Return the authenticated user's email address."""
        resp = await self._session.async_request("GET", USERINFO_URL)
        await _raise_for_status(resp)
        data = await resp.json()
        return data["email"]

    async def async_list_notes(self) -> list[dict[str, Any]]:
        """Return every non-trashed note in the account (all pages)."""
        notes: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = {"pageSize": "100", "filter": "trashed=false"}
            if page_token:
                params["pageToken"] = page_token
            resp = await self._session.async_request("GET", f"{API_BASE_URL}/notes", params=params)
            await _raise_for_status(resp)
            data = await resp.json()
            notes.extend(data.get("notes", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return notes

    async def async_create_list_note(self, title: str, item_texts: list[str]) -> dict[str, Any]:
        """Create a new checklist note with the given title and item texts."""
        body = {
            "title": title,
            "body": {
                "list": {
                    "listItems": [{"text": {"text": text}, "checked": False} for text in item_texts]
                }
            },
        }
        resp = await self._session.async_request("POST", f"{API_BASE_URL}/notes", json=body)
        await _raise_for_status(resp)
        return await resp.json()

    async def async_delete_note(self, name: str) -> None:
        """Delete a note by its resource name (e.g. 'notes/abc123')."""
        resp = await self._session.async_request("DELETE", f"{API_BASE_URL}/{name}")
        if resp.status == 404:
            return
        await _raise_for_status(resp)


async def _raise_for_status(resp) -> None:
    if resp.status >= 400:
        text = await resp.text()
        raise GoogleKeepApiError(f"HTTP {resp.status} from Google Keep API: {text}")


def top_level_item_texts(note: dict[str, Any]) -> list[str]:
    """Extract active (unchecked, non-nested) item texts from a note, in order.

    Checked items are dropped: this integration treats "checked" the same as
    "deleted" in both directions, since the API can't preserve per-item state
    across the create+delete cycle any other way. Nested sub-items (Keep's
    one level of checklist indentation) have no equivalent in Home
    Assistant's flat todo model and are dropped too.
    """
    items = note.get("body", {}).get("list", {}).get("listItems", [])
    texts = []
    for item in items:
        if item.get("checked"):
            continue
        texts.append(item.get("text", {}).get("text", ""))
    return texts


def is_list_note(note: dict[str, Any]) -> bool:
    """Return whether a note is a checklist note (vs. a plain text note)."""
    return "list" in note.get("body", {})
