"""Collector – listens to Home Assistant and records what happens and who did it."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_FINAL_WRITE,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, Event, HomeAssistant, State, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_DOMAINS,
    ACTOR_AUTOMATION,
    ACTOR_DEVICE,
    ACTOR_EXTERNAL,
    ACTOR_HUMAN,
    ACTOR_PHYSICAL,
    ACTOR_SYSTEM,
    ATTRIBUTE_MIN_DELTA,
    CONF_AREAS,
    CONF_DOMAINS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_USERS,
    CONF_HUMIDITY_RISE,
    CONF_HUMIDITY_SENSORS,
    CONF_LUX_SENSOR,
    CONF_POWER_SENSORS,
    CONF_POWER_STEP,
    CONF_TEMP_SENSOR,
    CONF_WATER_MIN,
    CONF_WATER_SENSORS,
    CONF_WORKDAY_SENSOR,
    DEFAULT_DOMAINS,
    DEFAULT_HUMIDITY_RISE,
    DEFAULT_POWER_STEP,
    DEFAULT_WATER_MIN,
    DOMAIN,
    FLUSH_INTERVAL_S,
    KIND_ATTRIBUTE,
    KIND_RUN,
    KIND_SIGNAL,
    KIND_STATE,
    MANUAL_ACTORS,
    OVERRIDE_WINDOW_S,
    TRACKED_ATTRIBUTES,
)
from .detectors import (
    HumidityRiseDetector,
    PowerStepDetector,
    Signal,
    WaterUseDetector,
    is_flow_unit,
    to_litres,
    to_litres_per_min,
    to_watts,
)
from .store import EventRow, EventStore

_LOGGER = logging.getLogger(__name__)

EVENT_AUTOMATION_TRIGGERED = "automation_triggered"
EVENT_SCRIPT_STARTED = "script_started"

# Domains whose state is a timestamp of the last press / activation.
TIMESTAMP_DOMAINS = ("scene", "button", "input_button", "event")
# Domains with no area (whole household).
AREALESS_DOMAINS = ("person",)

_BAD_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)
_CONTEXT_CACHE = 4000


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Collector:
    """Records state changes, automation runs and detector signals."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: EventStore) -> None:
        self.hass = hass
        self.store = store
        opts = entry.options
        self.domains: set[str] = set(opts.get(CONF_DOMAINS) or DEFAULT_DOMAINS)
        self.areas: set[str] = set(opts.get(CONF_AREAS) or [])
        self.exclude_entities: set[str] = set(opts.get(CONF_EXCLUDE_ENTITIES) or [])
        self.exclude_users: set[str] = set(opts.get(CONF_EXCLUDE_USERS) or [])
        self.humidity_sensors: set[str] = set(opts.get(CONF_HUMIDITY_SENSORS) or [])
        self.power_sensors: set[str] = set(opts.get(CONF_POWER_SENSORS) or [])
        self.water_sensors: set[str] = set(opts.get(CONF_WATER_SENSORS) or [])
        self.humidity_rise = float(opts.get(CONF_HUMIDITY_RISE, DEFAULT_HUMIDITY_RISE))
        self.power_step = float(opts.get(CONF_POWER_STEP, DEFAULT_POWER_STEP))
        self.water_min = float(opts.get(CONF_WATER_MIN, DEFAULT_WATER_MIN))
        self.workday_sensor: str | None = opts.get(CONF_WORKDAY_SENSOR) or None
        self.lux_sensor: str | None = opts.get(CONF_LUX_SENSOR) or None
        self.temp_sensor: str | None = opts.get(CONF_TEMP_SENSOR) or None

        self._buffer: list[EventRow] = []
        self._contexts: OrderedDict[str, str] = OrderedDict()
        self._last_auto: dict[str, tuple[float, str, str]] = {}
        self._detectors: dict[str, Any] = {}
        self._tracked_cache: dict[str, tuple[bool, str | None]] = {}
        self._unsubs: list[Callable[[], None]] = []
        self.captured = 0
        self.manual_captured = 0

    # -- lifecycle -------------------------------------------------------------
    async def async_start(self) -> None:
        bus = self.hass.bus
        self._unsubs += [
            bus.async_listen(EVENT_STATE_CHANGED, self._on_state_changed),
            bus.async_listen(EVENT_AUTOMATION_TRIGGERED, self._on_run),
            bus.async_listen(EVENT_SCRIPT_STARTED, self._on_run),
            bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry),
            bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._on_registry),
            bus.async_listen(EVENT_HOMEASSISTANT_FINAL_WRITE, self._on_final_write),
            async_track_time_interval(
                self.hass, self._async_flush_timer, timedelta(seconds=FLUSH_INTERVAL_S)
            ),
        ]

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.async_flush()

    async def async_flush(self) -> int:
        self._tick_detectors(time.time())
        if not self._buffer:
            return 0
        rows, self._buffer = self._buffer, []
        try:
            return await self.hass.async_add_executor_job(self.store.write, rows)
        except Exception:  # noqa: BLE001 - never break HA because of our DB
            _LOGGER.exception("Pattern Pilot: writing %s events failed", len(rows))
            return 0

    async def _async_flush_timer(self, _now: Any) -> None:
        await self.async_flush()

    async def _on_final_write(self, _event: Event) -> None:
        await self.async_flush()

    @callback
    def _on_registry(self, _event: Event) -> None:
        self._tracked_cache.clear()

    # -- filtering ---------------------------------------------------------------
    def _lookup(self, entity_id: str, domain: str) -> tuple[bool, str | None]:
        """(tracked?, area_id) – cached."""
        cached = self._tracked_cache.get(entity_id)
        if cached is not None:
            return cached
        tracked = domain in self.domains and entity_id not in self.exclude_entities
        area: str | None = None
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry is not None:
            if entry.entity_category is not None or entry.platform == DOMAIN:
                tracked = False
            area = entry.area_id
            if area is None and entry.device_id:
                device = dr.async_get(self.hass).async_get(entry.device_id)
                area = device.area_id if device else None
        if tracked and self.areas and domain not in AREALESS_DOMAINS:
            tracked = area in self.areas
        result = (tracked, area)
        self._tracked_cache[entity_id] = result
        return result

    # -- attribution -------------------------------------------------------------
    def _remember(self, context: Context, entity_id: str) -> None:
        self._contexts[context.id] = entity_id
        self._contexts.move_to_end(context.id)
        while len(self._contexts) > _CONTEXT_CACHE:
            self._contexts.popitem(last=False)

    def _attribute(
        self, context: Context, entity_id: str, domain: str
    ) -> tuple[str, str | None, str | None]:
        """Return (actor, user_id, ref)."""
        ref = self._contexts.get(context.id)
        if ref is None and context.parent_id:
            ref = self._contexts.get(context.parent_id)
        if ref is not None and ref != entity_id:
            return ACTOR_AUTOMATION, context.user_id, ref
        if context.user_id:
            if context.user_id in self.exclude_users:
                return ACTOR_EXTERNAL, context.user_id, None
            return ACTOR_HUMAN, context.user_id, None
        if context.parent_id:
            return ACTOR_SYSTEM, None, None
        if domain in ACTION_DOMAINS:
            return ACTOR_PHYSICAL, None, None
        return ACTOR_DEVICE, None, None

    # -- context snapshot --------------------------------------------------------
    def _snapshot(self) -> dict[str, Any]:
        states = self.hass.states
        now = dt_util.now()
        day_type = "weekend" if now.weekday() >= 5 else "workday"
        if self.workday_sensor and (st := states.get(self.workday_sensor)):
            if st.state == "on":
                day_type = "workday"
            elif st.state == "off":
                day_type = "weekend" if now.weekday() >= 5 else "holiday"
        sun = None
        if st := states.get("sun.sun"):
            sun = "day" if st.state == "above_horizon" else "night"
        lux = None
        if self.lux_sensor and (st := states.get(self.lux_sensor)):
            lux = _float(st.state)
        temperature = None
        if self.temp_sensor and (st := states.get(self.temp_sensor)):
            if st.domain == "weather":
                temperature = _float(st.attributes.get("temperature"))
            else:
                temperature = _float(st.state)
        people = sum(1 for p in states.async_all("person") if p.state == "home")
        return {
            "day_type": day_type,
            "sun": sun,
            "lux": lux,
            "temperature": temperature,
            "people_home": people,
        }

    # -- event handlers ------------------------------------------------------------
    @callback
    def _on_run(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if not entity_id:
            return
        self._remember(event.context, entity_id)
        if event.event_type != EVENT_AUTOMATION_TRIGGERED:
            return
        if entity_id in self.exclude_entities:
            return
        ctx = event.context
        if ctx.user_id and ctx.user_id not in self.exclude_users:
            actor = ACTOR_HUMAN  # run manually from the UI
        else:
            actor = ACTOR_AUTOMATION
        source = event.data.get("source")
        self._add(
            EventRow(
                ts=event.time_fired.timestamp(),
                entity_id=entity_id,
                domain="automation",
                area=None,
                kind=KIND_RUN,
                old=None,
                new=str(source)[:120] if source else None,
                value=None,
                actor=actor,
                user_id=ctx.user_id,
                context_id=ctx.id,
            )
        )

    @callback
    def _on_state_changed(self, event: Event) -> None:
        entity_id: str = event.data["entity_id"]
        new: State | None = event.data.get("new_state")
        old: State | None = event.data.get("old_state")
        if new is None or old is None:
            return
        ts = new.last_updated.timestamp()

        if (
            entity_id in self.humidity_sensors
            or entity_id in self.power_sensors
            or entity_id in self.water_sensors
        ):
            self._feed_detector(entity_id, new, ts)
            return

        domain = new.domain
        if domain not in self.domains:
            return
        tracked, area = self._lookup(entity_id, domain)
        if not tracked:
            return

        if old.state != new.state:
            self._state_change(entity_id, domain, area, old, new, ts)
        elif domain in TRACKED_ATTRIBUTES:
            self._attribute_change(entity_id, domain, area, old, new, ts)

    # -- state / attribute changes ----------------------------------------------------
    def _state_change(
        self, entity_id: str, domain: str, area: str | None, old: State, new: State, ts: float
    ) -> None:
        if domain in TIMESTAMP_DOMAINS:
            if new.state in _BAD_STATES or old.state == STATE_UNAVAILABLE:
                return
            old_v = None
            new_v = (
                str(new.attributes.get("event_type") or "event")
                if domain == "event"
                else "activated"
            )
        else:
            if new.state in _BAD_STATES or old.state in _BAD_STATES:
                return
            old_v, new_v = old.state, new.state
        self._record(entity_id, domain, area, KIND_STATE, old_v, new_v, self._value(domain, new), new, ts)

    def _attribute_change(
        self, entity_id: str, domain: str, area: str | None, old: State, new: State, ts: float
    ) -> None:
        if new.state in _BAD_STATES:
            return
        for attr in TRACKED_ATTRIBUTES[domain]:
            ov, nv = old.attributes.get(attr), new.attributes.get(attr)
            if ov == nv or nv is None:
                continue
            of, nf = _float(ov), _float(nv)
            if of is not None and nf is not None:
                if abs(nf - of) < ATTRIBUTE_MIN_DELTA.get(attr, 0.0):
                    continue
            self._record(
                entity_id,
                domain,
                area,
                KIND_ATTRIBUTE,
                f"{attr}:{ov}",
                f"{attr}:{nv}",
                nf,
                new,
                ts,
            )
            return

    @staticmethod
    def _value(domain: str, state: State) -> float | None:
        attrs = state.attributes
        if domain == "light":
            return _float(attrs.get("brightness"))
        if domain == "cover":
            return _float(attrs.get("current_position"))
        if domain in ("climate", "water_heater"):
            return _float(attrs.get("temperature"))
        if domain == "fan":
            return _float(attrs.get("percentage"))
        if domain == "media_player":
            return _float(attrs.get("volume_level"))
        return _float(state.state)

    def _record(
        self,
        entity_id: str,
        domain: str,
        area: str | None,
        kind: str,
        old_v: str | None,
        new_v: str | None,
        value: float | None,
        state: State,
        ts: float,
    ) -> None:
        actor, user_id, ref = self._attribute(state.context, entity_id, domain)
        override = False
        if actor == ACTOR_AUTOMATION and ref:
            self._last_auto[entity_id] = (ts, ref, new_v or "")
        elif actor in MANUAL_ACTORS:
            last = self._last_auto.get(entity_id)
            if last and ts - last[0] <= OVERRIDE_WINDOW_S and new_v != last[2]:
                override = True
                ref = last[1]
            self._last_auto.pop(entity_id, None)
        self._add(
            EventRow(
                ts=ts,
                entity_id=entity_id,
                domain=domain,
                area=area,
                kind=kind,
                old=old_v,
                new=new_v,
                value=value,
                actor=actor,
                user_id=user_id,
                ref=ref,
                override=override,
                context_id=state.context.id,
                context=self._snapshot() if actor in MANUAL_ACTORS else None,
            )
        )

    # -- detectors -------------------------------------------------------------------
    def _feed_detector(self, entity_id: str, state: State, ts: float) -> None:
        raw = _float(state.state)
        if raw is None:
            return
        unit = state.attributes.get("unit_of_measurement")
        det = self._detectors.get(entity_id)
        value: float | None
        if entity_id in self.humidity_sensors:
            det = det or HumidityRiseDetector(rise=self.humidity_rise)
            value = raw
        elif entity_id in self.power_sensors:
            det = det or PowerStepDetector(step=self.power_step)
            value = to_watts(raw, unit)
        else:
            flow = is_flow_unit(unit)
            if det is None or det.flow != flow:
                det = WaterUseDetector(min_litres=self.water_min, flow=flow)
            value = to_litres_per_min(raw, unit) if flow else to_litres(raw, unit)
        self._detectors[entity_id] = det
        if value is None:
            return
        self._emit(entity_id, det.update(ts, value))

    def _tick_detectors(self, ts: float) -> None:
        for entity_id, det in self._detectors.items():
            if isinstance(det, WaterUseDetector):
                self._emit(entity_id, det.tick(ts))

    def _emit(self, entity_id: str, signals: list[Signal]) -> None:
        if not signals:
            return
        _, area = self._lookup(entity_id, "sensor")
        for sig in signals:
            self._add(
                EventRow(
                    ts=sig.ts,
                    entity_id=entity_id,
                    domain="sensor",
                    area=area,
                    kind=KIND_SIGNAL,
                    old=None,
                    new=sig.name,
                    value=sig.value,
                    actor=ACTOR_DEVICE,
                )
            )

    def _add(self, row: EventRow) -> None:
        self._buffer.append(row)
        self.captured += 1
        if row.actor in MANUAL_ACTORS:
            self.manual_captured += 1

    # -- diagnostics -------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        area_reg = ar.async_get(self.hass)
        return {
            "domains": sorted(self.domains),
            "areas": [
                (a.name if (a := area_reg.async_get_area(area_id)) else area_id)
                for area_id in sorted(self.areas)
            ],
            "detectors": {
                eid: type(det).__name__ for eid, det in self._detectors.items()
            },
            "buffered": len(self._buffer),
            "captured_since_start": self.captured,
            "manual_since_start": self.manual_captured,
        }
