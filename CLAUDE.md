# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

A Home Assistant custom integration (`custom_components/google_keep_todo/`)
that two-way syncs Google Keep lists with Home Assistant `todo` entities,
using Google's official Keep REST API over OAuth2 (not the unofficial
`gkeepapi`/master-token approach). See `README.md` for the full user-facing
explanation, including the important architectural constraint that drives
most of the code: **the Keep API has no update/patch method**, so every
change is implemented as create-a-new-note + delete-the-old-note.

## Commit messages

Use **Conventional Commits** (`type(scope): summary`) for every commit in
this repo, e.g.:

- `feat(todo): support moving items between positions`
- `fix(coordinator): handle duplicate list titles without crashing`
- `docs(readme): clarify OAuth consent screen setup`
- `ci(security): add trivy secret scanning`
- `chore(deps): bump ruff to 0.x`

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`,
`build`. Add a `!` (e.g. `feat!:`) or a `BREAKING CHANGE:` footer for
anything that changes user-facing config or entity behavior.

## Architecture

- `manifest.json` — no pip requirements (pure `aiohttp`/HA core, no
  third-party Keep client library).
- `application_credentials.py` — declares the Google OAuth authorization
  server; the user supplies their own Client ID/Secret (Keep has no
  first-party HA app).
- `config_flow.py` — `AbstractOAuth2FlowHandler` subclass. After OAuth,
  fetches the account email (for the unique ID/title) and asks for a
  comma-separated list of Keep list *titles* to sync (not IDs — see below).
  `OptionsFlow` lets these be changed later without redoing OAuth.
- `api.py` — thin async REST client (`GoogleKeepRestApi`) wrapping
  `notes.list` / `notes.create` / `notes.delete` via
  `config_entry_oauth2_flow.OAuth2Session.async_request` (handles token
  refresh automatically). Also has the pure helper functions
  `top_level_item_texts()` and `is_list_note()` used to parse a note's JSON
  body.
- `coordinator.py` — `GoogleKeepUpdateCoordinator` polls all notes, matches
  synced lists **by title** (a note's `name`/id changes every time it's
  recreated, so title is the only stable identifier available), and creates
  an empty note if a configured title doesn't exist yet. All writes go
  through `async_replace_items(title, item_texts)`: create new note, delete
  old note, then `async_request_refresh()`.
- `todo.py` — `GoogleKeepTodoListEntity`. Item `uid` is
  `sha1(text)[:12]` since the Keep API assigns no per-item ID — duplicate
  item text within one list is a known, documented limitation. Checking an
  item off deletes it (no durable "completed" state is possible given the
  no-update constraint).

## Working in this repo

- Lint/format: `ruff check .` and `ruff format .` (config in
  `pyproject.toml`). CI (`.github/workflows/ci.yml`) runs both, plus JSON
  validation, `hassfest`, and HACS repo validation, on every PR.
- Security: `.github/workflows/security.yml` runs a Trivy filesystem scan
  (vulnerabilities, secrets, misconfig) on every PR/push and weekly.
- There is no test suite or live Home Assistant instance available in this
  environment. When changing `api.py`/`coordinator.py`/`todo.py` logic,
  verify by hand: import the module against a real `homeassistant` +
  relevant dependency installed in a scratch venv, and/or exercise pure
  logic (item parsing, uid hashing, move/delete/update index math) with
  fake note payloads in a one-off script. Don't claim something works
  against live Google Keep or a live HA UI unless it was actually run that
  way — say plainly when a check was static/simulated instead.
- `main` is branch-protected: PRs must pass all CI status checks before
  merging (see repo settings). Don't force-push to `main`.
