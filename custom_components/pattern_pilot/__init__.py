"""Pattern Pilot – learns household routines and suggests automations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.util import dt as dt_util

from .collector import Collector
from .const import (
    CONF_ANALYSIS_TIME,
    CONF_HISTORY_DAYS,
    DB_FILENAME,
    DEFAULT_ANALYSIS_TIME,
    DEFAULT_HISTORY_DAYS,
    SIGNAL_STATS_UPDATED,
)
from .store import EventStore, StoreStats

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
STATS_INTERVAL = timedelta(minutes=5)


@dataclass
class PatternPilotData:
    """Runtime data of the config entry."""

    store: EventStore
    collector: Collector
    stats: StoreStats = field(default_factory=StoreStats)
    last_maintenance: str | None = None


type PatternPilotConfigEntry = ConfigEntry[PatternPilotData]


def _parse_time(value: str) -> tuple[int, int, int]:
    parts = [int(p) for p in (value or DEFAULT_ANALYSIS_TIME).split(":")]
    parts += [0] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


async def async_setup_entry(hass: HomeAssistant, entry: PatternPilotConfigEntry) -> bool:
    """Set up Pattern Pilot."""
    store = EventStore(hass.config.path(DB_FILENAME))
    await hass.async_add_executor_job(store.open)
    collector = Collector(hass, entry, store)
    data = PatternPilotData(store=store, collector=collector)
    entry.runtime_data = data

    async def refresh_stats(_now=None) -> None:
        day_start = dt_util.start_of_local_day().timestamp()
        data.stats = await hass.async_add_executor_job(store.stats, day_start)
        async_dispatcher_send(hass, SIGNAL_STATS_UPDATED)

    async def maintenance(_now=None) -> None:
        await collector.async_flush()
        keep = int(entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))
        removed = await hass.async_add_executor_job(store.purge, keep)
        if dt_util.now().weekday() == 6:
            await hass.async_add_executor_job(store.vacuum)
        data.last_maintenance = dt_util.now().isoformat()
        _LOGGER.debug("Pattern Pilot maintenance: %s old events removed", removed)
        await refresh_stats()

    async def flush_and_refresh(_now=None) -> None:
        await collector.async_flush()
        await refresh_stats()

    await collector.async_start()
    await refresh_stats()

    hour, minute, second = _parse_time(entry.options.get(CONF_ANALYSIS_TIME, DEFAULT_ANALYSIS_TIME))
    timers = [
        async_track_time_change(hass, maintenance, hour=hour, minute=minute, second=second),
        async_track_time_interval(hass, flush_and_refresh, STATS_INTERVAL),
    ]

    def cancel_timers() -> None:
        while timers:
            timers.pop()()

    async def on_stop(_event: Event) -> None:
        cancel_timers()
        await collector.async_stop()

    entry.async_on_unload(cancel_timers)
    entry.async_on_unload(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, on_stop))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PatternPilotConfigEntry) -> bool:
    """Unload Pattern Pilot."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = entry.runtime_data
        await data.collector.async_stop()
        await hass.async_add_executor_job(data.store.close)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: PatternPilotConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
