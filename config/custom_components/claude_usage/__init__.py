"""Claude Usage integration for Home Assistant."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_CF_CLEARANCE, CONF_ORG_ID, CONF_SESSION_KEY, DOMAIN
from .coordinator import ClaudeUsageCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ClaudeUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (Settings → Integrations → ⋮ → Download diagnostics)."""
    coordinator: ClaudeUsageCoordinator = hass.data[DOMAIN][entry.entry_id]
    m = coordinator.metrics

    return {
        "config": {
            # Credentials are masked — only show length and prefix for debugging
            CONF_SESSION_KEY: _mask(entry.data.get(CONF_SESSION_KEY, "")),
            CONF_CF_CLEARANCE: _mask(entry.data.get(CONF_CF_CLEARANCE, "")),
            CONF_ORG_ID: entry.data.get(CONF_ORG_ID, ""),
        },
        "metrics": {
            "total_requests": m.total_requests,
            "failed_requests": m.failed_requests,
            "success_rate_pct": _success_rate(m.total_requests, m.failed_requests),
            "cookie_renewals": m.cookie_renewals,
            "last_success_at": m.last_success_at,
            "last_response_ms": m.last_response_ms,
        },
        "last_data": coordinator.data,
    }


def _mask(value: str) -> str:
    """Show only the first 10 chars followed by ***."""
    if not value:
        return ""
    return value[:10] + "***"


def _success_rate(total: int, failed: int) -> float | None:
    if total == 0:
        return None
    return round((total - failed) / total * 100, 1)
