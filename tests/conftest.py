"""Shared fixtures for Claude Usage integration tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from aiohttp import ClientResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.claude_usage.const import (
    CONF_CF_CLEARANCE,
    CONF_ORG_ID,
    CONF_SESSION_KEY,
    DOMAIN,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def verify_cleanup():
    """Override the HA plugin's strict thread/task cleanup check.

    The upstream fixture incorrectly flags the asyncio executor shutdown thread
    (`_run_safe_shutdown_loop`) created by Python 3.12 as a leaked resource.
    Custom-component test suites conventionally disable this check.
    """
    yield


class _CompatClientResponse(ClientResponse):
    """ClientResponse accepting aioresponses' pre-aiohttp-3.14 constructor call."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("stream_writer", MagicMock())
        super().__init__(*args, **kwargs)


@pytest.fixture(autouse=True)
def aioresponses_aiohttp_314_compat():
    """Let aioresponses 0.7.9 build responses with aiohttp >= 3.14.

    aiohttp 3.14 made `stream_writer` a required ClientResponse argument and
    aioresponses does not pass it yet (pnuckowski/aioresponses#288).
    Remove once a fixed aioresponses release is pinned.
    """
    with patch("aioresponses.core.ClientResponse", _CompatClientResponse):
        yield


ORG_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SESSION_KEY = "sk-ant-session-fakekey"
CF_CLEARANCE = "fake-cf-clearance-value"


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """A pre-built config entry with fake credentials."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_entry_id",
        data={
            CONF_SESSION_KEY: SESSION_KEY,
            CONF_CF_CLEARANCE: CF_CLEARANCE,
            CONF_ORG_ID: ORG_ID,
        },
    )


@pytest.fixture
def fake_raw_api_data() -> dict:
    """Raw payload as returned by the claude.ai API (before _transform)."""
    return {
        "five_hour": {"utilization": 42.0, "resets_at": "2026-04-14T05:00:00+00:00"},
        "seven_day": {"utilization": 70.0, "resets_at": "2026-04-21T00:00:00+00:00"},
        "seven_day_sonnet": {"utilization": 55.0, "resets_at": "2026-04-21T00:00:00+00:00"},
        "seven_day_opus": None,
        "iguana_necktie": {
            "utilization": 10.0,
            "resets_at": "2026-11-05T07:59:00+00:00",
            "limit_dollars": 250,
            "used_dollars": 25.0,
            "remaining_dollars": 225.0,
        },
        "extra_usage": {
            "is_enabled": True,
            "monthly_limit": 2000,
            "used_credits": 10.0,
            "utilization": None,
        },
        "limits": [
            {"kind": "session", "percent": 42, "severity": "normal", "is_active": True},
            {"kind": "weekly_all", "percent": 70, "severity": "warning", "is_active": False},
            {
                "kind": "weekly_scoped",
                "percent": 30,
                "severity": "normal",
                "resets_at": "2026-04-21T00:00:00+00:00",
                "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
                "is_active": False,
            },
        ],
        "seven_day_breakdown": {
            "rows": [
                {"key": "claude_code", "display_name": "Claude Code", "percent": 80},
                {"key": "chat", "display_name": "Chats", "percent": 20},
                {"key": "cowork", "display_name": "Cowork", "percent": 0},
                {"key": "other", "display_name": "Autres", "percent": 0},
            ],
        },
        "weekly_scoped_shares": [
            {"limit_index": 2, "used_percent_of_weekly": 15, "allowance_percent_of_weekly": 50}
        ],
    }


@pytest.fixture
def fake_usage_data() -> dict:
    """Transformed usage payload (output of _transform) used to populate coordinator.data."""
    return {
        "session_5h": {"utilization": 42, "resets_in_minutes": 180},
        "weekly": {"utilization": 70, "resets_in_minutes": 2000},
        "weekly_sonnet": {"utilization": 55},
        "weekly_opus": None,
        "extra_usage": {"used": 10, "utilization": 5},
    }
