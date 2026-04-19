DOMAIN = "claude_usage"

CONF_SESSION_KEY = "session_key"
CONF_CF_CLEARANCE = "cf_clearance"
CONF_ORG_ID = "org_id"

CONF_UPDATE_INTERVAL = "update_interval"
UPDATE_INTERVAL = 60        # seconds (default)
UPDATE_INTERVAL_MIN = 10    # seconds (minimum)
UPDATE_INTERVAL_MAX = 21600 # seconds (maximum = 6 h)

BASE_URL = "https://claude.ai"
USAGE_ENDPOINT = "/api/organizations/{org_id}/usage"
