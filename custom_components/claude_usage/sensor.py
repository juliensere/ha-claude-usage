"""Sensor platform for Claude Usage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClaudeUsageCoordinator


@dataclass(kw_only=True)
class ClaudeUsageSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value extractor.

    value_fn   : reads from coordinator.data  (usage sensors)
    metric_fn  : reads from coordinator.metrics  (diagnostic sensors)
    When metric_fn is set it takes priority over value_fn.
    """
    value_fn: Callable[[dict], Any] = field(default=lambda _: None)
    metric_fn: Callable[[Any], Any] | None = field(default=None)
    attrs_fn: Callable[[dict], dict[str, Any] | None] | None = field(default=None)


_SLOT_ATTRS = ("severity", "is_active", "resets_at")
_SCOPED_ATTRS = (
    *_SLOT_ATTRS,
    "used_percent_of_weekly",
    "allowance_percent_of_weekly",
)


def _slot_attrs(slot: dict | None, keys: tuple[str, ...] = _SLOT_ATTRS) -> dict | None:
    if not slot:
        return None
    return {key: slot.get(key) for key in keys}


def _scoped_limit(data: dict, key: str) -> dict | None:
    return next(
        (s for s in data.get("scoped_limits") or [] if s.get("key") == key), None
    )


def _scoped_description(scoped: dict) -> ClaudeUsageSensorDescription:
    """Build the sensor description for one model/surface-scoped weekly limit."""
    key = scoped["key"]
    return ClaudeUsageSensorDescription(
        key=f"weekly_scoped_{key}",
        name=f"Weekly {scoped['name']} Usage",
        icon="mdi:robot-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_scoped_limit(d, key) or {}).get("utilization"),
        attrs_fn=lambda d: _slot_attrs(_scoped_limit(d, key), _SCOPED_ATTRS),
    )


SENSORS: tuple[ClaudeUsageSensorDescription, ...] = (
    ClaudeUsageSensorDescription(
        key="session_utilization",
        name="Session Usage",
        icon="mdi:clock-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("session_5h") or {}).get("utilization"),
        attrs_fn=lambda d: _slot_attrs(d.get("session_5h")),
    ),
    ClaudeUsageSensorDescription(
        key="session_reset_minutes",
        name="Session Resets In",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("session_5h") or {}).get("resets_in_minutes"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_utilization",
        name="Weekly Usage",
        icon="mdi:calendar-week",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("weekly") or {}).get("utilization"),
        attrs_fn=lambda d: _slot_attrs(d.get("weekly")),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_reset_minutes",
        name="Weekly Resets In",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("weekly") or {}).get("resets_in_minutes"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_sonnet",
        name="Weekly Sonnet Usage",
        icon="mdi:robot-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            (d["weekly_sonnet"] or {}).get("utilization")
            if d.get("weekly_sonnet")
            else None
        ),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_opus",
        name="Weekly Opus Usage",
        icon="mdi:robot",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            (d["weekly_opus"] or {}).get("utilization")
            if d.get("weekly_opus")
            else None
        ),
    ),
    ClaudeUsageSensorDescription(
        key="extra_credits_used",
        name="Extra Credits Used",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="credits",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("extra_usage") or {}).get("used"),
    ),
    ClaudeUsageSensorDescription(
        key="extra_utilization",
        name="Extra Usage",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("extra_usage") or {}).get("utilization"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_share_claude_code",
        name="Weekly Share Claude Code",
        icon="mdi:console",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("breakdown") or {}).get("claude_code"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_share_chat",
        name="Weekly Share Chats",
        icon="mdi:chat-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("breakdown") or {}).get("chat"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_share_cowork",
        name="Weekly Share Cowork",
        icon="mdi:account-group-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("breakdown") or {}).get("cowork"),
    ),
    ClaudeUsageSensorDescription(
        key="weekly_share_other",
        name="Weekly Share Other",
        icon="mdi:dots-horizontal-circle-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("breakdown") or {}).get("other"),
    ),
    ClaudeUsageSensorDescription(
        key="credit_used",
        name="Credit Used",
        icon="mdi:cash-minus",
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("credit") or {}).get("used"),
        attrs_fn=lambda d: _slot_attrs(d.get("credit"), ("utilization", "resets_at")),
    ),
    ClaudeUsageSensorDescription(
        key="credit_remaining",
        name="Credit Remaining",
        icon="mdi:cash-check",
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("credit") or {}).get("remaining"),
    ),
    ClaudeUsageSensorDescription(
        key="credit_limit",
        name="Credit Limit",
        icon="mdi:cash-lock",
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("credit") or {}).get("limit"),
    ),
)


DIAGNOSTIC_SENSORS: tuple[ClaudeUsageSensorDescription, ...] = (
    ClaudeUsageSensorDescription(
        key="diag_total_requests",
        name="Total Requests",
        icon="mdi:counter",
        native_unit_of_measurement="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        metric_fn=lambda m: m.total_requests,
    ),
    ClaudeUsageSensorDescription(
        key="diag_failed_requests",
        name="Failed Requests",
        icon="mdi:alert-circle-outline",
        native_unit_of_measurement="requests",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        metric_fn=lambda m: m.failed_requests,
    ),
    ClaudeUsageSensorDescription(
        key="diag_response_time",
        name="Response Time",
        icon="mdi:timer-outline",
        native_unit_of_measurement="ms",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        metric_fn=lambda m: m.last_response_ms,
    ),
    ClaudeUsageSensorDescription(
        key="diag_cookie_renewals",
        name="Cookie Renewals",
        icon="mdi:cookie-refresh-outline",
        native_unit_of_measurement="renewals",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        metric_fn=lambda m: m.cookie_renewals,
    ),
    ClaudeUsageSensorDescription(
        key="diag_last_success",
        name="Last Successful Update",
        icon="mdi:check-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        metric_fn=lambda m: m.last_success_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ClaudeUsageCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Scoped weekly limits depend on the plan: one sensor per limit seen at setup
    scoped = tuple(
        _scoped_description(s)
        for s in (coordinator.data or {}).get("scoped_limits") or []
    )
    async_add_entities(
        ClaudeUsageSensor(coordinator, description)
        for description in (*SENSORS, *scoped, *DIAGNOSTIC_SENSORS)
    )


class ClaudeUsageSensor(CoordinatorEntity[ClaudeUsageCoordinator], SensorEntity):
    """A single Claude Usage sensor entity."""

    entity_description: ClaudeUsageSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ClaudeUsageCoordinator,
        description: ClaudeUsageSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Claude Usage",
            manufacturer="Anthropic",
            model="Claude Max",
        )

    @property
    def native_value(self) -> Any:
        if self.entity_description.metric_fn is not None:
            # Diagnostic sensor — reads from coordinator.metrics (always available)
            return self.entity_description.metric_fn(self.coordinator.metrics)
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None or self.coordinator.data is None:
            return None
        return attrs_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        if self.entity_description.metric_fn is not None:
            # Diagnostic sensors are available as soon as the coordinator exists
            return True
        return super().available and self.coordinator.data is not None
