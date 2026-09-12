"""Constants for the Google Keep Todo Sync integration."""

DOMAIN = "google_keep_todo"

OAUTH2_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH2_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 - not a secret
OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/keep",
    "openid",
    "email",
]

API_BASE_URL = "https://keep.googleapis.com/v1"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

CONF_LIST_TITLES = "list_titles"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30  # seconds - the API has no push mechanism; be a reasonable citizen
