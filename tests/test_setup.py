"""End-to-end test: load the integration in a real Home Assistant core.

This is the test that catches Home Assistant API removals: it goes through
config entry setup, entity creation and unload with a captured API payload.
"""
from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.claude_usage.const import BASE_URL, USAGE_ENDPOINT

from .conftest import ORG_ID

_USAGE_URL = BASE_URL + USAGE_ENDPOINT.format(org_id=ORG_ID)
_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "usage_2026_10.json").read_text()
)


async def test_setup_creates_sensors_and_unloads(
    hass: HomeAssistant, aioclient_mock, mock_entry, enable_custom_integrations
):
    """Setup with a real payload creates every sensor, then unloads cleanly."""
    mock_entry.add_to_hass(hass)

    aioclient_mock.get(_USAGE_URL, json=_PAYLOAD)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.LOADED

    def state(entity_id: str):
        return hass.states.get(f"sensor.claude_usage_{entity_id}")

    assert state("session_usage").state == "47.0"
    assert state("session_usage").attributes["severity"] == "normal"
    assert state("weekly_usage").state == "12.0"
    assert state("weekly_share_claude_code").state == "100"
    assert state("credit_remaining").state == "250.0"
    assert state("total_requests").state == "1"

    # One sensor per scoped weekly limit found in the payload
    assert state("weekly_fable_usage").state == "0"
    assert state("weekly_fable_usage").attributes["allowance_percent_of_weekly"] == 50

    # 15 usage + 1 scoped + 5 diagnostic
    assert len(hass.states.async_all("sensor")) == 21

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
