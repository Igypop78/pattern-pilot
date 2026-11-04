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
    EVENT_CALL_SERVICE,
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

from .const import (
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
    CONF_SENSITIVITY,
    DEFAULT_DOMAINS,
    DEFAULT_SENSITIVITY,
    DOMAIN,
    FLUSH_INTERVAL_S,
    KIND_ATTRIBUTE,
    KIND_RUN,
    KIND_SIGNAL,
    KIND_STATE,
    MANUAL_ACTORS,
    MEASURE_DEVICE_CLASSES,
    OVERRIDE_WINDOW_S,
    PAIR_WINDOW_S,
    PHYSICAL_MANUAL_DOMAINS,
    PULSE_DOMAINS,
    PULSE_S,
    TRACKED_ATTRIBUTES,
)
from .context import ContextProvider
from .detectors import FLOORS, ChangeDetector, CounterRate, Signal, normalize
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
        self.sensitivity: str = opts.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
        self.counters: set[str] = set()
        self.context = ContextProvider(hass)

        self._buffer: list[EventRow] = []
        self._contexts: OrderedDict[str, str] = OrderedDict()
        self._last_auto: dict[str, tuple[float, str, str]] = {}
        # entity → (ts, actor, user_id, ref) of the last command sent from HA
        self._pending: dict[str, tuple[float, str, str | None, str | None]] = {}
        # entity → (ts, old, new) of the last uncommanded change (pulse detection)
        self._last_change: dict[str, tuple[float, str | None, str | None]] = {}
        self.paired = 0
        self.pulses = 0
        self._detectors: dict[str, ChangeDetector] = {}
        self._rates: dict[str, CounterRate] = {}
        self._sensor_kind: dict[str, str | None] = {}
        self._profiles: dict[str, dict] = {}
        self._tracked_cache: dict[str, tuple[bool, str | None]] = {}
        self._unsubs: list[Callable[[], None]] = []
        self.captured = 0
        self.manual_captured = 0

    # -- lifecycle -------------------------------------------------------------
    async def async_start(self) -> None:
        self._profiles = await self.hass.async_add_executor_job(self.store.load_profiles)
        self.counters = await _energy_counters(self.hass)
        await self.context.async_prepare()
        bus = self.hass.bus
        self._unsubs += [
            bus.async_listen(EVENT_STATE_CHANGED, self._on_state_changed),
            bus.async_listen(EVENT_AUTOMATION_TRIGGERED, self._on_run),
            bus.async_listen(EVENT_SCRIPT_STARTED, self._on_run),
            bus.async_listen(EVENT_CALL_SERVICE, self._on_call_service),
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
        await self.async_save_profiles()

    async def async_save_profiles(self) -> None:
        profiles = {eid: det.profile() for eid, det in self._detectors.items()}
        if not profiles:
            return
        try:
            await self.hass.async_add_executor_job(self.store.save_profiles, profiles)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Pattern Pilot: saving detector profiles failed")

    async def async_refresh(self) -> None:
        """Nightly: reload Energy panel counters, holidays, weather entity."""
        self.counters = await _energy_counters(self.hass)
        self._sensor_kind.clear()
        await self.context.async_prepare()

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
        self._sensor_kind.clear()

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
        if domain in PHYSICAL_MANUAL_DOMAINS:
            return ACTOR_PHYSICAL, None, None
        return ACTOR_DEVICE, None, None

    # -- commands from HA (paired with late confirmations) ---------------------------
    def _targets(self, data: dict[str, Any]) -> set[str]:
        ids: set[str] = set()

        def as_list(value: Any) -> list[str]:
            if isinstance(value, str):
                return [v.strip() for v in value.split(",") if v.strip()]
            if isinstance(value, (list, tuple, set)):
                return [str(v) for v in value]
            return []

        ids.update(e for e in as_list(data.get("entity_id")) if "." in e)
        devices = set(as_list(data.get("device_id")))
        areas = as_list(data.get("area_id"))
        if areas or devices:
            ent_reg = er.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)
            for area_id in areas:
                ids.update(e.entity_id for e in er.async_entries_for_area(ent_reg, area_id))
                devices.update(d.id for d in dr.async_entries_for_area(dev_reg, area_id))
            for device_id in devices:
                ids.update(
                    e.entity_id
                    for e in er.async_entries_for_device(ent_reg, device_id)
                    if e.area_id is None or not areas or e.area_id in areas
                )
        return ids

    @callback
    def _on_call_service(self, event: Event) -> None:
        domain = event.data.get("domain")
        if domain in (DOMAIN, "system_log", "logbook", "recorder", "notify", "persistent_notification"):
            return
        try:
            ids = self._targets(event.data.get("service_data") or {})
        except Exception:  # noqa: BLE001 - never break HA because of us
            return
        if not ids:
            return
        ts = event.time_fired.timestamp()
        for entity_id in ids:
            actor, user_id, ref = self._attribute(event.context, entity_id, "")
            if actor in (ACTOR_PHYSICAL, ACTOR_DEVICE):
                actor = ACTOR_SYSTEM  # a command without origin = some integration
            self._pending[entity_id] = (ts, actor, user_id, ref)
        if len(self._pending) > 2000:
            cutoff = ts - PAIR_WINDOW_S
            self._pending = {k: v for k, v in self._pending.items() if v[0] >= cutoff}

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

        domain = new.domain
        if domain not in self.domains:
            return
        if domain == "sensor":
            self._feed_sensor(entity_id, new, ts)
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
        cmd = self._pending.get(entity_id)
        if kind == KIND_STATE and domain not in TIMESTAMP_DOMAINS:
            last = self._last_change.get(entity_id)
            if (
                domain in PULSE_DOMAINS
                and last
                and ts - last[0] <= PULSE_S
                and new_v == last[1]
                and old_v == last[2]
                and actor not in (ACTOR_HUMAN, ACTOR_AUTOMATION, ACTOR_EXTERNAL)
                and (cmd is None or cmd[0] <= last[0])  # no new command for the way back
            ):
                # went back by itself (gate impulse, doorbell) – one action, not two
                self._last_change.pop(entity_id, None)
                self.pulses += 1
                return
            self._last_change[entity_id] = (ts, old_v, new_v)
        if actor in (ACTOR_PHYSICAL, ACTOR_DEVICE, ACTOR_SYSTEM):
            if cmd and 0 <= ts - cmd[0] <= PAIR_WINDOW_S:
                actor, user_id, ref = cmd[1], cmd[2], cmd[3]
                self.paired += 1
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
                context=self.context.snapshot() if actor in MANUAL_ACTORS else None,
            )
        )

    # -- sensors → rise / fall events ---------------------------------------------------
    def _classify(self, entity_id: str, state: State) -> str | None:
        """'counter', 'measure' or None (cached)."""
        if entity_id in self._sensor_kind:
            return self._sensor_kind[entity_id]
        kind: str | None = None
        tracked, _area = self._lookup(entity_id, "sensor")
        if entity_id in self.counters:
            if entity_id not in self.exclude_entities:
                kind = "counter"
        elif tracked:
            attrs = state.attributes
            if (
                attrs.get("state_class") == "measurement"
                and attrs.get("device_class") in MEASURE_DEVICE_CLASSES
            ):
                kind = "measure"
        self._sensor_kind[entity_id] = kind
        return kind

    def _feed_sensor(self, entity_id: str, state: State, ts: float) -> None:
        kind = self._classify(entity_id, state)
        if kind is None:
            return
        raw = _float(state.state)
        if raw is None:
            return
        device_class = state.attributes.get("device_class")
        if kind == "counter":
            rate = self._rates.setdefault(entity_id, CounterRate()).update(ts, raw)
            if rate is None:
                return
            self._emit(entity_id, "counter", self._detector(entity_id, None).update(ts, rate))
            return
        value = normalize(device_class, raw, state.attributes.get("unit_of_measurement"))
        if value is None:
            return
        self._emit(entity_id, device_class, self._detector(entity_id, device_class).update(ts, value))

    def _detector(self, entity_id: str, device_class: str | None) -> ChangeDetector:
        det = self._detectors.get(entity_id)
        if det is None:
            det = ChangeDetector(
                floor=FLOORS.get(device_class or "", 1e-6),
                sensitivity=self.sensitivity,
                profile=self._profiles.pop(entity_id, None),
            )
            self._detectors[entity_id] = det
        return det

    def _tick_detectors(self, ts: float) -> None:
        for entity_id, rate in self._rates.items():
            zero = rate.tick(ts)
            if zero is not None and entity_id in self._detectors:
                self._emit(entity_id, "counter", self._detectors[entity_id].update(ts, zero))

    def _emit(self, entity_id: str, source: str | None, signals: list[Signal]) -> None:
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
                    old=source,
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
            "sensitivity": self.sensitivity,
            "energy_counters": sorted(self.counters),
            "sensors_watched": len(self._detectors),
            "sensors_ready": sum(
                1 for det in self._detectors.values() if det.is_ready(time.time())
            ),
            "context": self.context.describe(),
            "buffered": len(self._buffer),
            "paired_with_command": self.paired,
            "pulses_merged": self.pulses,
            "captured_since_start": self.captured,
            "manual_since_start": self.manual_captured,
        }


async def _energy_counters(hass: HomeAssistant) -> set[str]:
    """Counters configured in the Energy dashboard (grid, solar, battery, gas, water, devices)."""
    try:
        from homeassistant.components.energy.data import (  # noqa: PLC0415
            async_get_manager,
        )

        manager = await async_get_manager(hass)
        data = manager.data or {}
    except Exception:  # noqa: BLE001 - energy not set up
        return set()
    found: set[str] = set()
    skip = ("stat_cost", "stat_compensation", "stat_rate")

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str):
                    if key.startswith("stat_") and key not in skip and "." in value and ":" not in value:
                        found.add(value)
                else:
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return found
