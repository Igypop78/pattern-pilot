"""WebSocket API for the Igy Pattern Pilot card."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MIN_DAYS_FOR_ANALYSIS, VERSION

HOURLY_DAYS = 14


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register commands once."""
    if hass.data.get(f"{DOMAIN}_ws"):
        return
    hass.data[f"{DOMAIN}_ws"] = True
    websocket_api.async_register_command(hass, ws_overview)


def _entry_data(hass: HomeAssistant) -> Any:
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = getattr(entry, "runtime_data", None)
        if data is not None:
            return data
    return None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@websocket_api.async_response
async def ws_overview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Everything the card shows, in one call."""
    data = _entry_data(hass)
    if data is None:
        connection.send_error(msg["id"], "not_loaded", "Pattern Pilot is not loaded")
        return
    await data.collector.async_flush()
    now = dt_util.now()
    today = dt_util.start_of_local_day()
    since_hourly = (today - timedelta(days=HOURLY_DAYS)).timestamp()
    since_week = (now - timedelta(days=7)).timestamp()
    ov = await hass.async_add_executor_job(
        data.store.overview, since_hourly, since_week
    )

    # manual actions per local hour: today vs. average of previous days
    today_ts = today.timestamp()
    hourly_today = [0] * 24
    hourly_sum = [0] * 24
    past_days: set[str] = set()
    for ts in ov.pop("manual_ts"):
        local = dt_util.as_local(dt_util.utc_from_timestamp(ts))
        if ts >= today_ts:
            hourly_today[local.hour] += 1
        else:
            hourly_sum[local.hour] += 1
            past_days.add(local.date().isoformat())
    n_days = max(1, len(past_days))
    hourly_avg = [round(v / n_days, 2) for v in hourly_sum] if past_days else None

    stats = data.stats
    first = stats.first_ts
    ready_from = (
        dt_util.as_local(dt_util.utc_from_timestamp(first) + timedelta(days=MIN_DAYS_FOR_ANALYSIS))
        .date()
        .isoformat()
        if first
        else None
    )
    desc = data.collector.describe()
    connection.send_result(
        msg["id"],
        {
            "version": VERSION,
            "status": "ready" if stats.days >= MIN_DAYS_FOR_ANALYSIS else "collecting",
            "days": stats.days,
            "days_needed": MIN_DAYS_FOR_ANALYSIS,
            "ready_from": ready_from,
            "first_event": first,
            "events_total": stats.total,
            "events_today": stats.today,
            "manual_today": stats.manual_today,
            "db_mb": round(stats.size_bytes / 1_000_000, 2),
            "sensors_watched": desc["sensors_watched"],
            "sensors_ready": desc["sensors_ready"],
            "energy_counters": len(desc["energy_counters"]),
            "sensitivity": desc["sensitivity"],
            "hourly_today": hourly_today,
            "hourly_avg": hourly_avg,
            "hourly_days": len(past_days),
            **ov,
        },
    )
