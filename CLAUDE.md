# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

A Home Assistant custom integration (`custom_components/google_keep_todo/`)
that two-way syncs Google Keep lists with Home Assistant `todo` entities,
using `gkeepapi` (an unofficial Keep client) authenticated with a Google
master token. See `README.md` for full user-facing setup instructions.

## Important history: don't re-attempt the official OAuth API

An earlier version of this integration used Google's *official* Keep REST
API over standard OAuth2 (`application_credentials` +
`config_entry_oauth2_flow`), specifically to avoid the master-token/
dedicated-account trust model. That was reverted after confirming in
production that **the Keep API's OAuth scopes
(`https://www.googleapis.com/auth/keep` /
`.../auth/keep.readonly`) are not available to personal `@gmail.com`
accounts at all** - the scope doesn't even appear as selectable in the
OAuth consent screen's scope picker for a personal-account Google Cloud
project, and requesting it anyway fails at the authorization endpoint with
`Error 400: invalid_scope`. This appears to be a hard Workspace-only gate
on Google's side, not a configuration problem fixable from this project.
Do not resurrect the OAuth-based design without first independently
reconfirming this has changed on Google's side.

The official API also had a second, independent problem even if the scope
issue were resolved: `notes.create` / `notes.list` / `notes.get` /
`notes.delete` exist, but there is no update/patch method for a note or an
item, so it could only support sync via delete-and-recreate of the whole
note - losing durable checked-item state and per-item identity. The
`gkeepapi` approach used now supports real in-place updates via
`keep.sync()`, which is strictly better fidelity in addition to being the
only option that actually works for a personal account.

## Commit messages

Use **Conventional Commits** (`type(scope): summary`) for every commit in
this repo, e.g.:

- `feat(todo): support moving items between positions`
- `fix(coordinator): handle duplicate list titles without crashing`
- `docs(readme): clarify master token setup steps`
- `ci(security): add trivy secret scanning`
- `chore(deps): bump gkeepapi to 0.x`

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`,
`build`. Add a `!` (e.g. `feat!:`) or a `BREAKING CHANGE:` footer for
anything that changes user-facing config or entity behavior.

## Architecture

- `manifest.json` — pins `gkeepapi` as the only pip requirement.
- `api.py` — `GoogleKeepApi`, a blocking wrapper around `gkeepapi.Keep`
  (`authenticate`, `sync`, `dump`, `get_lists`, `get_list`, `create_list`).
  Everything in it is synchronous and must be called via
  `hass.async_add_executor_job`.
- `config_flow.py` — collects email + master token, validates by calling
  `authenticate()`, then shows a multi-select of the account's existing
  Keep lists. Has a `reauth` flow (triggered automatically via
  `ConfigEntryAuthFailed` if the token stops working) and an `OptionsFlow`
  to change synced lists/poll interval later without redoing auth.
- `coordinator.py` — `GoogleKeepUpdateCoordinator` owns one `gkeepapi.Keep`
  session per config entry. `_async_update_data` calls `keep.sync()` (pulls
  remote changes) and reads the selected lists. `async_execute(mutation)`
  is the single write path: run a blocking mutation against already-loaded
  gkeepapi node objects (marks them dirty), then `async_request_refresh()`
  triggers another `sync()`, which pushes the dirty nodes up *and* pulls
  anything else that changed - this is what makes it two-way. State is
  persisted via `keep.dump()`/`Store` so a Home Assistant restart doesn't
  need a full resync.
- `todo.py` — `GoogleKeepTodoListEntity`. Item `uid` is the gkeepapi node's
  own stable `.id` (client-generated at creation, persists across syncs).
  Reordering computes a new numeric `.sort` value between neighbors
  (`gkeepapi.node.List.SORT_DELTA`); indented Keep sub-items are excluded
  from `todo_items` (no HA equivalent) but left alone on the Keep side.

## Working in this repo

- Lint/format: `ruff check .` and `ruff format .` (config in
  `pyproject.toml`). CI (`.github/workflows/ci.yml`) runs both, plus JSON
  validation, `hassfest`, and HACS repo validation, on every PR.
- Security: `.github/workflows/security.yml` runs a Trivy filesystem scan
  (vulnerabilities, secrets, misconfig) on every PR/push and weekly.
- There is no test suite or live Home Assistant instance available in this
  environment, and no real Google master token to test against. When
  changing `api.py`/`coordinator.py`/`todo.py` logic, verify by hand:
  install the real `gkeepapi` + `homeassistant` packages in a scratch venv
  and import the modules to catch API-signature mismatches, and exercise
  pure logic (item ordering, sort-based move math, checked/delete
  semantics) against real `gkeepapi.node.List`/`ListItem` objects
  constructed locally (no network needed for that part). Don't claim
  something works against a live Google account or a live HA UI unless it
  was actually run that way - say plainly when a check was static/
  simulated instead.
- `main` is branch-protected: PRs must pass all CI status checks before
  merging (see repo settings). Don't force-push to `main`.
- The `custom_components/google_keep_todo/brand/` folder holds
  `icon.png`/`icon@2x.png` served via Home Assistant's brands proxy API
  (HA 2026.3+, no manifest.json opt-in needed) - this is independent of
  the auth mechanism and wasn't affected by the OAuth revert.
