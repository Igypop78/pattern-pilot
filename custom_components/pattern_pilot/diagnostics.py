"""Diagnostics for Pattern Pilot."""

from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any

from homeassistant.core import HomeAssistant

from . import PatternPilotConfigEntry
from .const import CONF_EXCLUDE_USERS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PatternPilotConfigEntry
) -> dict[str, Any]:
    """Return diagnostics (local download only)."""
    data = entry.runtime_data
    options = dict(entry.options)
    if options.get(CONF_EXCLUDE_USERS):
        options[CONF_EXCLUDE_USERS] = f"{len(options[CONF_EXCLUDE_USERS])} user(s)"
    recent = await hass.async_add_executor_job(data.store.recent, 30)
    top = await hass.async_add_executor_job(data.store.top_entities, time.time() - 86400, 25)
    for row in recent:
        row.pop("user_id", None)
    return {
        "options": options,
        "stats": asdict(data.stats),
        "collector": data.collector.describe(),
        "last_maintenance": data.last_maintenance,
        "top_entities_24h": top,
        "recent_events": recent,
    }
