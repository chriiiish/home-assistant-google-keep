# Google Keep Todo Sync for Home Assistant

## 1. Overview

![Google Keep Todo Sync screenshot](docs/screenshot.png)
<!-- TODO: replace with a real screenshot of a synced todo.* entity in the Home Assistant UI -->

Two-way sync between Google Keep lists and Home Assistant `todo` lists.
Create, check off, edit, delete, or reorder items on either side and it
flows to the other within one poll interval (60 seconds by default).

This uses [`gkeepapi`](https://github.com/kiwiz/gkeepapi), an unofficial
Google Keep client. Google's *official* Keep API only grants its OAuth
scopes to Google Workspace accounts - a personal `@gmail.com` account
cannot use it at all (confirmed by an `invalid_scope` error: the scope
isn't even selectable on a personal project's OAuth consent screen). For a
personal account, `gkeepapi` is the only way to automate Keep at all, and
it authenticates with a Google **master token** instead of your normal
password/2FA - a token with full account access which, once you have it,
does not expire on its own.

> [!IMPORTANT]
> A master token grants full access to the associated Google account, not
> just Keep. See the security recommendation below before setting this up.

## 2. Installation

### HACS (custom repository)
1. HACS → ⋮ → Custom repositories → add this repository's
   URL as an "Integration".
2. Install "Google Keep Todo Sync", then restart Home Assistant.

### Manual
Copy `custom_components/google_keep_todo` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

## 3. Configuration

### Step 1: Use a dedicated Google account (strongly recommended)

Because a master token grants full access to the associated Google account
(not just Keep), **do not use your primary Google account**. Instead:

1. Create a new, dedicated Google account just for this integration.
2. In Google Keep, share the list(s) you want to sync from your main account
   with that new account's email address (Keep's "Collaborator" sharing).
3. Obtain the master token for the **new** account (see below) and use that
   account's email/token in this integration's setup.

This way, if the token is ever leaked, only a throwaway account with access
to a handful of shared lists is exposed - not your primary Google identity.

### Step 2: Obtain a master token

`gkeepapi` cannot log in with just a password anymore - Google blocks that
as suspicious. The easiest way to get a master token is a small community
Docker tool that automates the browser-login exchange:

```
docker run -it --rm breph/ha-google-home_get-token:latest python3 get_tokens.py
```

Run this on a separate machine from Home Assistant (any Linux box, or
Windows via WSL) and follow its prompts to sign in to the **dedicated**
account. It prints a master token (starts with `aas_et/`) - copy the whole
thing.

<details>
<summary>Manual alternative, if you'd rather not use Docker</summary>

1. Log in to the dedicated Google account in a private/incognito browser
   window at `https://accounts.google.com/EmbeddedSetup`, completing any
   2FA prompts.
2. Open DevTools → Application/Storage → Cookies, and copy the value of the
   `oauth_token` cookie for `accounts.google.com`.
3. Run:
   ```python
   import gpsoauth
   android_id = "0000000000000000"  # any stable 16-hex-digit string; keep it
   email = "your-dedicated-account@gmail.com"
   oauth_token = "the cookie value from step 2"
   master_response = gpsoauth.exchange_token(email, oauth_token, android_id)
   print(master_response["Token"])
   ```
</details>

Save the token somewhere safe. You will not need to repeat this unless it's
revoked (e.g. you change the dedicated account's password).

### Step 3: Add the integration

1. Settings → Devices & Services → Add Integration → **Google Keep Todo
   Sync**.
2. Enter the dedicated account's email and the master token from step 2.
3. Select which Keep lists to sync. Each becomes its own `todo.*` entity.

### Changing settings later

Use the integration's **Configure** option to change which lists are
synced or adjust the poll interval (default 60s; Keep has no push API, so
lower values increase the number of requests made to Google - 30s is the
practical floor).

## 4. How the sync works & limitations

- Home Assistant polls Google Keep every `scan_interval` seconds and pulls
  down any remote changes.
- Any change made from the Home Assistant `todo` UI/API (create, check off,
  rename, delete, reorder) is applied to the local Keep list object
  immediately and pushed to Google right away, not just on the next poll.
- Conflicts are resolved by Google Keep's own sync protocol - the same
  mechanism the official Keep apps use, so behavior matches what you'd see
  syncing two Keep clients.
- Google Keep supports one level of indented sub-items on a list; Home
  Assistant's `todo` entity model is flat, so indented sub-items are not
  shown in Home Assistant and are left untouched on the Keep side.
- State (Keep's local node cache) is persisted across Home Assistant
  restarts so it doesn't need a full resync every time it starts up - only
  the master token needs to be entered once.
- No due dates or descriptions - Google Keep list items don't have them.
- This relies on an unofficial, reverse-engineered API. Google could change
  or block it at any time. If your master token stops working, the
  integration will prompt you to re-authenticate with a new one.

## 5. Development / Contribution

Issues and pull requests are welcome - please open an issue first for
anything beyond a small fix so we can agree on the approach.

If this integration is useful to you and you'd like to support its
development:

<a href="https://buymeacoffee.com/chris.lloyd" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="41" width="174">
</a>
