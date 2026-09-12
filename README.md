# Google Keep Todo Sync for Home Assistant

## 1. Overview

![Google Keep Todo Sync screenshot](docs/screenshot.png)
<!-- TODO: replace with a real screenshot of a synced todo.* entity in the Home Assistant UI -->

Two-way sync between Google Keep lists and Home Assistant `todo` lists,
using Google's **official** Keep API over standard OAuth2 - no master
token, no dedicated Google account, no unofficial/reverse-engineered
client. Add, check off, rename, delete, or reorder items from either Home
Assistant or the Keep app and it flows to the other side within one poll
interval (60 seconds by default).

> [!IMPORTANT]
> The official Keep API has no way to update a note or an item in place -
> only create, list, get, and delete whole notes. So **every change is
> implemented as delete-and-recreate**: this integration rebuilds the full
> item list and creates a brand new note, then deletes the old one. Two
> consequences of that are worth knowing up front:
> - **Checking an item off deletes it** - there's no way to persist
>   "checked" state through a delete+recreate cycle.
> - **Items have no stable ID**, so Home Assistant identifies each item by
>   a hash of its text - keep item text unique within a list.
>
> See [section 4](#4-how-the-sync-works--limitations) for the full
> explanation and other limitations.

## 2. Installation

### HACS (custom repository)
1. HACS → Integrations → ⋮ → Custom repositories → add this repository's
   URL as an "Integration".
2. Install "Google Keep Todo Sync", then restart Home Assistant.

### Manual
Copy `custom_components/google_keep_todo` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

## 3. Configuration

### Step 1: Create a Google Cloud OAuth client (one-time)

Google Keep has no official Home Assistant app to authorize against, so you
register your own:

1. Create or pick a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the [Keep API](https://console.cloud.google.com/apis/library/keep.googleapis.com)
   for that project.
3. Go to **APIs & Services → OAuth consent screen**:
   - Add the scope `https://www.googleapis.com/auth/keep`.
   - Add your own Google account as a **test user**.
   - Set publishing status to **In production** (leaving it in "Testing"
     causes Google to expire your refresh token every 7 days, which would
     silently break the integration on a weekly basis). This is safe for
     personal use with under 100 users - Google will still show an
     "unverified app" warning the first time you authorize, which you click
     through; full verification (and the security assessment it requires)
     is not needed at this scale.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth
   client ID**, type **Web application**, and add
   `https://my.home-assistant.io/redirect/oauth` as an authorized redirect
   URI (add your own instance's `<url>/auth/external/callback` too if you
   don't use My Home Assistant redirects).
5. Note the Client ID and Client Secret.

### Step 2: Add the application credential in Home Assistant

1. Settings → Devices & Services → Application Credentials → Add →
   select **Google Keep Todo Sync**, and enter the Client ID/Secret from
   step 1.

### Step 3: Add the integration

1. Settings → Devices & Services → Add Integration → **Google Keep Todo
   Sync**, and complete the Google sign-in/consent flow.
2. Enter the Keep list titles to sync, comma-separated (e.g.
   `Groceries, Chores`). Each becomes its own `todo.*` entity. If a list
   with that title doesn't already exist in Keep, it's created empty.

### Changing settings later

Use the integration's **Configure** option to change which list titles are
synced or adjust the poll interval (default 60s; the API has no push
mechanism, so lower values just mean more frequent polling - 30s is the
practical floor).

## 4. How the sync works & limitations

- Home Assistant polls Google Keep every `scan_interval` seconds for the
  current state of each synced list (matched by title).
- Any change from the Home Assistant `todo` UI/API (add, rename, check off,
  delete, reorder) is pushed immediately: the full new item list is written
  to a newly created note, and the previous note is deleted.
- A Keep list is matched by **title**, not by its underlying note ID -
  every recreation gets a new ID, so keep each synced list's title unique
  in the account.
- Nested/indented Keep checklist sub-items have no equivalent in Home
  Assistant's flat `todo` model and are dropped from what's shown in Home
  Assistant (existing sub-items in Keep are left alone unless the parent
  list is rewritten by a Home Assistant-side edit, at which point they are
  not carried over).
- No due dates or descriptions - Keep list items don't have them.
- No durable "completed" state - checking an item off deletes it.
- No stable per-item identity - duplicate item text within one list will
  collide.
- Every write recreates the whole note, so collaborators viewing the note
  in the Keep app will see it "flicker" (old note gone, new one appears)
  rather than an in-place edit.

If you need real per-item state (durable checked items, distinguishable
duplicate text, etc.), that's only possible via the unofficial `gkeepapi`
client and a Google master token - a materially different trust/security
model that this integration deliberately avoids.

## 5. Development / Contribution

Issues and pull requests are welcome - please open an issue first for
anything beyond a small fix so we can agree on the approach, especially
given the delete-and-recreate sync model's constraints described above.

If this integration is useful to you and you'd like to support its
development:

<a href="https://buymeacoffee.com/chris.lloyd" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="41" width="174">
</a>
