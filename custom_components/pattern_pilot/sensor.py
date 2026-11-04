"""Sensors of Pattern Pilot (v0.1: data collection status)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PatternPilotConfigEntry, PatternPilotData
from .const import DOMAIN, MIN_DAYS_FOR_ANALYSIS, NAME, SIGNAL_STATS_UPDATED, VERSION

STATUS_COLLECTING = "collecting"
STATUS_READY = "ready"


def _ts(value: float | None) -> datetime | None:
    return dt_util.utc_from_timestamp(value) if value else None


@dataclass(frozen=True, kw_only=True)
class PPSensorDescription(SensorEntityDescription):
    """Sensor description with value getters."""

    value_fn: Callable[[PatternPilotData], Any]
    attrs_fn: Callable[[PatternPilotData], dict[str, Any]] | None = None


def _status(d: PatternPilotData) -> str:
    return STATUS_READY if d.stats.days >= MIN_DAYS_FOR_ANALYSIS else STATUS_COLLECTING


def _status_attrs(d: PatternPilotData) -> dict[str, Any]:
    s = d.stats
    return {
        "days_of_data": s.days,
        "days_needed": MIN_DAYS_FOR_ANALYSIS,
        "progress": min(100, round(100 * s.days / MIN_DAYS_FOR_ANALYSIS)),
        "events_total": s.total,
        "manual_actions_total": s.manual_total,
        "first_event": _ts(s.first_ts),
        "last_event": _ts(s.last_ts),
        "by_actor": s.by_actor,
        "by_kind": s.by_kind,
        "last_maintenance": d.last_maintenance,
        "version": VERSION,
    }


SENSORS: tuple[PPSensorDescription, ...] = (
    PPSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[STATUS_COLLECTING, STATUS_READY],
        value_fn=_status,
        attrs_fn=_status_attrs,
    ),
    PPSensorDescription(
        key="days_of_data",
        translation_key="days_of_data",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda d: d.stats.days,
    ),
    PPSensorDescription(
        key="events",
        translation_key="events",
        value_fn=lambda d: d.stats.total,
    ),
    PPSensorDescription(
        key="events_today",
        translation_key="events_today",
        value_fn=lambda d: d.stats.today,
    ),
    PPSensorDescription(
        key="manual_actions_today",
        translation_key="manual_actions_today",
        value_fn=lambda d: d.stats.manual_today,
    ),
    PPSensorDescription(
        key="database_size",
        translation_key="database_size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: round(d.stats.size_bytes / 1_000_000, 2),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PatternPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors."""
    async_add_entities(PatternPilotSensor(entry, desc) for desc in SENSORS)


class PatternPilotSensor(SensorEntity):
    """A Pattern Pilot sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: PPSensorDescription

    def __init__(self, entry: PatternPilotConfigEntry, description: PPSensorDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # Stable, language independent entity_id.
        self.entity_id = f"sensor.{DOMAIN}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Igypop78",
            model="Pattern Pilot",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATS_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._entry.runtime_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self._entry.runtime_data)
