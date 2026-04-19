"""DataUpdateCoordinator for Claude Usage."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed


def _minutes_until(iso: str) -> int | None:
    """Return minutes between now and an ISO timestamp, or None on failure."""
    try:
        dt = datetime.fromisoformat(iso)
        now = datetime.now(timezone.utc)
        return max(0, int((dt - now).total_seconds() / 60))
    except Exception:
        return None


def _parse_slot(raw: dict, key: str) -> dict | None:
    """Extract a usage slot from the raw API response and compute resets_in_minutes."""
    entry = raw.get(key)
    if not entry:
        return None
    resets_at = entry.get("resets_at")
    return {
        "utilization": entry.get("utilization") or 0.0,
        "resets_at": resets_at,
        "resets_in_minutes": _minutes_until(resets_at) if resets_at else None,
    }


def _transform(raw: dict) -> dict:
    """Transform the raw claude.ai API response into the structure expected by sensors."""
    extra = raw.get("extra_usage") or {}
    used = extra.get("used_credits") or 0.0
    limit = extra.get("monthly_limit") or 0
    return {
        "session_5h": _parse_slot(raw, "five_hour"),
        "weekly": _parse_slot(raw, "seven_day"),
        "weekly_sonnet": _parse_slot(raw, "seven_day_sonnet"),
        "weekly_opus": _parse_slot(raw, "seven_day_opus"),
        "extra_usage": {
            "enabled": extra.get("is_enabled", False),
            "used": used,
            "limit": limit,
            "utilization": round(used / limit * 100, 1) if limit else 0.0,
        },
    }

from .const import (
    BASE_URL,
    CONF_CF_CLEARANCE,
    CONF_ORG_ID,
    CONF_SESSION_KEY,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    UPDATE_INTERVAL,
    USAGE_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class UsageMetrics:
    """Accumulates plugin-level metrics across polling cycles."""
    total_requests: int = 0
    failed_requests: int = 0
    cookie_renewals: int = 0
    last_success_at: str | None = None   # ISO timestamp
    last_response_ms: int | None = None  # Duration of last successful call

# Headers that pass Cloudflare — mirrors scripts/check_session_usage.py
_BROWSER_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,fr;q=0.8",
    "accept-encoding": "gzip, deflate",
    "referer": "https://claude.ai/settings/usage",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def validate_credentials(
    session_key: str, cf_clearance: str, org_id: str
) -> dict:
    """
    Try a real API call and return the parsed data.
    Raises ConfigEntryAuthFailed or aiohttp.ClientError on failure.
    Used both by config_flow (validation) and coordinator (data fetch).
    """
    url = BASE_URL + USAGE_ENDPOINT.format(org_id=org_id)
    headers = {
        **_BROWSER_HEADERS,
        "cookie": (
            f"sessionKey={quote(session_key, safe='')}; "
            f"cf_clearance={quote(cf_clearance, safe='')}"
        ),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
            allow_redirects=False,
        ) as resp:
            if resp.status in (401, 403):
                body = await resp.text()
                if any(
                    x in body.lower()
                    for x in ("cloudflare", "just a moment", "cf-ray")
                ):
                    raise ConfigEntryAuthFailed("cf_clearance_expired")
                raise ConfigEntryAuthFailed("session_expired")

            if resp.status == 302:
                # Redirect to login page
                raise ConfigEntryAuthFailed("session_expired")

            if resp.status != 200:
                raise UpdateFailed(f"Unexpected HTTP status: {resp.status}")

            body = await resp.text()
            try:
                raw = json.loads(body)
            except ValueError:
                _LOGGER.warning(
                    "Non-JSON response from API (content-type: %s): %.200s",
                    resp.content_type,
                    body,
                )
                raise UpdateFailed("Non-JSON response from API")
            return _transform(raw), resp.cookies


class ClaudeUsageCoordinator(DataUpdateCoordinator[dict]):
    """Fetches Claude usage data every minute and auto-renews cookies."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = int(entry.options.get(CONF_UPDATE_INTERVAL, UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self.metrics = UsageMetrics()

    async def _async_update_data(self) -> dict:
        session_key = self.entry.data[CONF_SESSION_KEY]
        cf_clearance = self.entry.data[CONF_CF_CLEARANCE]
        org_id = self.entry.data[CONF_ORG_ID]

        url = BASE_URL + USAGE_ENDPOINT.format(org_id=org_id)
        headers = {
            **_BROWSER_HEADERS,
            "cookie": (
                f"sessionKey={quote(session_key, safe='')}; "
                f"cf_clearance={quote(cf_clearance, safe='')}"
            ),
        }

        self.metrics.total_requests += 1
        t_start = time.monotonic()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=False,
                ) as resp:

                    if resp.status in (401, 403):
                        self.metrics.failed_requests += 1
                        body = await resp.text()
                        if any(
                            x in body.lower()
                            for x in ("cloudflare", "just a moment", "cf-ray")
                        ):
                            raise ConfigEntryAuthFailed("cf_clearance_expired")
                        raise ConfigEntryAuthFailed("session_expired")

                    if resp.status == 302:
                        self.metrics.failed_requests += 1
                        raise ConfigEntryAuthFailed("session_expired")

                    if resp.status != 200:
                        self.metrics.failed_requests += 1
                        raise UpdateFailed(f"HTTP {resp.status}")

                    body = await resp.text()
                    try:
                        raw = json.loads(body)
                    except ValueError:
                        self.metrics.failed_requests += 1
                        _LOGGER.warning(
                            "Non-JSON response from API (content-type: %s): %.200s",
                            resp.content_type,
                            body,
                        )
                        raise UpdateFailed("Non-JSON response from API")
                    _LOGGER.debug("Raw API response: %s", raw)
                    data = _transform(raw)

                    # Record response time and success timestamp
                    self.metrics.last_response_ms = int(
                        (time.monotonic() - t_start) * 1000
                    )
                    self.metrics.last_success_at = datetime.now(timezone.utc).isoformat()

                    # Auto-renew cookies if the server issues new ones
                    updates: dict = {}
                    if "cf_clearance" in resp.cookies:
                        new_val = resp.cookies["cf_clearance"].value
                        if new_val and new_val != cf_clearance:
                            updates[CONF_CF_CLEARANCE] = new_val
                            self.metrics.cookie_renewals += 1
                            _LOGGER.debug("cf_clearance renewed automatically")
                    if "sessionKey" in resp.cookies:
                        new_val = resp.cookies["sessionKey"].value
                        if new_val and new_val != session_key:
                            updates[CONF_SESSION_KEY] = new_val
                            _LOGGER.debug("sessionKey renewed automatically")

                    if updates:
                        self.hass.config_entries.async_update_entry(
                            self.entry,
                            data={**self.entry.data, **updates},
                        )

                    return data

        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientError as err:
            self.metrics.failed_requests += 1
            raise UpdateFailed(f"Network error: {err}") from err
