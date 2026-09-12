"""Constants for the Google Keep Todo Sync integration."""

DOMAIN = "google_keep_todo"

CONF_MASTER_TOKEN = "master_token"
CONF_LIST_IDS = "list_ids"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 30  # seconds - avoid hammering Keep's unofficial API

STORAGE_VERSION = 1
