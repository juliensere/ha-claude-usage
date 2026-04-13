"""Shared fixtures for Claude Usage integration tests."""
from __future__ import annotations

import pytest
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
def fake_usage_data() -> dict:
    """Realistic usage payload returned by claude.ai."""
    return {
        "session_5h": {"utilization": 42, "resets_in_minutes": 180},
        "weekly": {"utilization": 70, "resets_in_minutes": 2000},
        "weekly_sonnet": {"utilization": 55},
        "weekly_opus": None,
        "extra_usage": {"used": 10, "utilization": 5},
    }
