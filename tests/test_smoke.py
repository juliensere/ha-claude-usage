"""Smoke tests for the Claude Usage integration.

Coverage:
  - validate_credentials: success / auth failure / Cloudflare block / network error
  - ClaudeUsageCoordinator._async_update_data: success path + metrics update
  - ClaudeUsageCoordinator._async_update_data: auth failure increments failed_requests
  - ClaudeUsageSensor.native_value: usage sensor reads from coordinator.data
  - ClaudeUsageSensor.native_value: diagnostic sensor reads from coordinator.metrics
  - ClaudeUsageSensor.available: usage sensor unavailable when data is None
  - ClaudeUsageSensor.available: diagnostic sensor always available
  - __init__._mask / _success_rate helpers
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.claude_usage.__init__ import _mask, _success_rate
from custom_components.claude_usage.const import BASE_URL, DOMAIN, USAGE_ENDPOINT
from custom_components.claude_usage.coordinator import (
    ClaudeUsageCoordinator,
    UsageMetrics,
    validate_credentials,
)
from custom_components.claude_usage.sensor import (
    DIAGNOSTIC_SENSORS,
    SENSORS,
    ClaudeUsageSensor,
)

from .conftest import CF_CLEARANCE, ORG_ID, SESSION_KEY

_USAGE_URL = BASE_URL + USAGE_ENDPOINT.format(org_id=ORG_ID)

# ── validate_credentials ────────────────────────────────────────────────────


async def test_validate_credentials_success(fake_usage_data):
    """HTTP 200 → returns parsed JSON without raising."""
    with aioresponses() as m:
        m.get(_USAGE_URL, payload=fake_usage_data, status=200)
        result, _cookies = await validate_credentials(SESSION_KEY, CF_CLEARANCE, ORG_ID)

    assert result["session_5h"]["utilization"] == 42


async def test_validate_credentials_session_expired():
    """HTTP 401 without Cloudflare body → ConfigEntryAuthFailed('session_expired')."""
    with aioresponses() as m:
        m.get(_USAGE_URL, body="Unauthorized", status=401)
        with pytest.raises(ConfigEntryAuthFailed, match="session_expired"):
            await validate_credentials(SESSION_KEY, CF_CLEARANCE, ORG_ID)


async def test_validate_credentials_cloudflare_block():
    """HTTP 403 with Cloudflare body → ConfigEntryAuthFailed('cf_clearance_expired')."""
    with aioresponses() as m:
        m.get(_USAGE_URL, body="Just a moment... cloudflare", status=403)
        with pytest.raises(ConfigEntryAuthFailed, match="cf_clearance_expired"):
            await validate_credentials(SESSION_KEY, CF_CLEARANCE, ORG_ID)


async def test_validate_credentials_302_redirect():
    """HTTP 302 → ConfigEntryAuthFailed('session_expired')."""
    with aioresponses() as m:
        m.get(_USAGE_URL, status=302, headers={"Location": "https://claude.ai/login"})
        with pytest.raises(ConfigEntryAuthFailed, match="session_expired"):
            await validate_credentials(SESSION_KEY, CF_CLEARANCE, ORG_ID)


async def test_validate_credentials_unexpected_status():
    """HTTP 500 → UpdateFailed."""
    with aioresponses() as m:
        m.get(_USAGE_URL, status=500, body="Internal Server Error")
        with pytest.raises(UpdateFailed, match="500"):
            await validate_credentials(SESSION_KEY, CF_CLEARANCE, ORG_ID)


# ── ClaudeUsageCoordinator ──────────────────────────────────────────────────


async def test_coordinator_success_updates_metrics(
    hass: HomeAssistant, mock_entry, fake_usage_data
):
    """Successful fetch updates data and increments total_requests / last_response_ms."""
    mock_entry.add_to_hass(hass)
    coordinator = ClaudeUsageCoordinator(hass, mock_entry)

    with aioresponses() as m:
        m.get(_USAGE_URL, payload=fake_usage_data, status=200)
        data = await coordinator._async_update_data()

    assert data["session_5h"]["utilization"] == 42
    assert coordinator.metrics.total_requests == 1
    assert coordinator.metrics.failed_requests == 0
    assert coordinator.metrics.last_response_ms is not None
    assert coordinator.metrics.last_success_at is not None


async def test_coordinator_auth_failure_increments_failed(
    hass: HomeAssistant, mock_entry
):
    """Auth failure increments failed_requests and re-raises ConfigEntryAuthFailed."""
    mock_entry.add_to_hass(hass)
    coordinator = ClaudeUsageCoordinator(hass, mock_entry)

    with aioresponses() as m:
        m.get(_USAGE_URL, body="Unauthorized", status=401)
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    assert coordinator.metrics.total_requests == 1
    assert coordinator.metrics.failed_requests == 1


async def test_coordinator_cookie_renewal(
    hass: HomeAssistant, mock_entry, fake_usage_data
):
    """When server sends a new cf_clearance cookie, cookie_renewals is incremented."""
    mock_entry.add_to_hass(hass)
    coordinator = ClaudeUsageCoordinator(hass, mock_entry)

    with aioresponses() as m:
        m.get(
            _USAGE_URL,
            payload=fake_usage_data,
            status=200,
            headers={"Set-Cookie": "cf_clearance=new-clearance-value; Path=/"},
        )
        await coordinator._async_update_data()

    assert coordinator.metrics.cookie_renewals == 1


# ── UsageMetrics defaults ────────────────────────────────────────────────────


def test_usage_metrics_defaults():
    m = UsageMetrics()
    assert m.total_requests == 0
    assert m.failed_requests == 0
    assert m.cookie_renewals == 0
    assert m.last_success_at is None
    assert m.last_response_ms is None


# ── Sensor native_value ──────────────────────────────────────────────────────


def _make_sensor(coordinator, description):
    """Instantiate a ClaudeUsageSensor without going through HA entity registry."""
    sensor = ClaudeUsageSensor.__new__(ClaudeUsageSensor)
    sensor.coordinator = coordinator
    sensor.entity_description = description
    return sensor


def test_usage_sensor_reads_value_fn(fake_usage_data):
    """Usage sensor extracts the correct value from coordinator.data."""
    coordinator = MagicMock()
    coordinator.data = fake_usage_data

    session_desc = next(s for s in SENSORS if s.key == "session_utilization")
    sensor = _make_sensor(coordinator, session_desc)
    assert sensor.native_value == 42


def test_usage_sensor_none_when_data_missing():
    """Usage sensor returns None when coordinator.data is None."""
    coordinator = MagicMock()
    coordinator.data = None

    session_desc = next(s for s in SENSORS if s.key == "session_utilization")
    sensor = _make_sensor(coordinator, session_desc)
    assert sensor.native_value is None


def test_usage_sensor_nullable_field(fake_usage_data):
    """weekly_opus sensor returns None gracefully when the field is None."""
    coordinator = MagicMock()
    coordinator.data = fake_usage_data  # weekly_opus is None in the fixture

    opus_desc = next(s for s in SENSORS if s.key == "weekly_opus")
    sensor = _make_sensor(coordinator, opus_desc)
    assert sensor.native_value is None


def test_diagnostic_sensor_reads_metric_fn():
    """Diagnostic sensor calls metric_fn on coordinator.metrics."""
    metrics = UsageMetrics(total_requests=7, failed_requests=2)
    coordinator = MagicMock()
    coordinator.metrics = metrics

    total_desc = next(s for s in DIAGNOSTIC_SENSORS if s.key == "diag_total_requests")
    sensor = _make_sensor(coordinator, total_desc)
    assert sensor.native_value == 7


# ── Sensor available ─────────────────────────────────────────────────────────


def test_usage_sensor_unavailable_when_no_data():
    """Usage sensor.available is False when coordinator.data is None."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = None

    session_desc = next(s for s in SENSORS if s.key == "session_utilization")
    sensor = ClaudeUsageSensor.__new__(ClaudeUsageSensor)
    sensor.coordinator = coordinator
    sensor.entity_description = session_desc
    # Bypass CoordinatorEntity.available by calling the property directly
    assert sensor.available is False


def test_diagnostic_sensor_always_available():
    """Diagnostic sensor.available is True regardless of coordinator state."""
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = None
    coordinator.metrics = UsageMetrics()

    diag_desc = next(s for s in DIAGNOSTIC_SENSORS if s.key == "diag_total_requests")
    sensor = ClaudeUsageSensor.__new__(ClaudeUsageSensor)
    sensor.coordinator = coordinator
    sensor.entity_description = diag_desc
    assert sensor.available is True


# ── Helper functions ─────────────────────────────────────────────────────────


def test_mask_short_value():
    assert _mask("abc") == "abc***"


def test_mask_long_value():
    result = _mask("sk-ant-session-supersecrettoken")
    assert result == "sk-ant-ses***"
    assert "supersecrettoken" not in result


def test_mask_empty():
    assert _mask("") == ""


def test_success_rate_normal():
    assert _success_rate(100, 10) == 90.0


def test_success_rate_zero_total():
    assert _success_rate(0, 0) is None


def test_success_rate_all_failed():
    assert _success_rate(5, 5) == 0.0
