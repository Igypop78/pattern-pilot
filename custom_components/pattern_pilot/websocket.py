"""WebSocket API for the Igy Pattern Pilot card."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    MIN_DAYS_FOR_ANALYSIS,
    SIGNAL_SUGGESTIONS_UPDATED,
    SNOOZE_DAYS,
    STATUS_NEW,
    SUGGESTION_STATUSES,
    VERSION,
)

HOURLY_DAYS = 14


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register commands once."""
    if hass.data.get(f"{DOMAIN}_ws"):
        return
    hass.data[f"{DOMAIN}_ws"] = True
    websocket_api.async_register_command(hass, ws_overview)
    websocket_api.async_register_command(hass, ws_suggestions)
    websocket_api.async_register_command(hass, ws_update)
    websocket_api.async_register_command(hass, ws_analyze)


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


async def _suggestions_payload(hass: HomeAssistant, data: Any) -> dict[str, Any]:
    items = await hass.async_add_executor_job(data.store.list_suggestions)
    return {
        "suggestions": items,
        "last_analysis": data.last_analysis,
        "analyzing": data.analyzing,
        "days": data.stats.days,
        "days_needed": MIN_DAYS_FOR_ANALYSIS,
        "preliminary": data.stats.days < MIN_DAYS_FOR_ANALYSIS,
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/suggestions"})
@websocket_api.async_response
async def ws_suggestions(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """All suggestions with their status."""
    data = _entry_data(hass)
    if data is None:
        connection.send_error(msg["id"], "not_loaded", "Pattern Pilot is not loaded")
        return
    connection.send_result(msg["id"], await _suggestions_payload(hass, data))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/suggestion/update",
        vol.Required("suggestion_id"): str,
        vol.Required("status"): vol.In(SUGGESTION_STATUSES),
        vol.Optional("automation_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Accept / snooze / reject / restore a suggestion."""
    data = _entry_data(hass)
    if data is None:
        connection.send_error(msg["id"], "not_loaded", "Pattern Pilot is not loaded")
        return
    ok = await hass.async_add_executor_job(
        data.store.set_suggestion_status,
        msg["suggestion_id"],
        msg["status"],
        msg.get("automation_id"),
        SNOOZE_DAYS,
    )
    if not ok:
        connection.send_error(msg["id"], "not_found", "Suggestion not found")
        return
    items = await hass.async_add_executor_job(data.store.list_suggestions)
    data.suggestions_new = sum(1 for s in items if s["status"] == STATUS_NEW)
    async_dispatcher_send(hass, SIGNAL_SUGGESTIONS_UPDATED)
    connection.send_result(msg["id"], await _suggestions_payload(hass, data))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/analyze"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_analyze(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run the analysis now."""
    data = _entry_data(hass)
    if data is None:
        connection.send_error(msg["id"], "not_loaded", "Pattern Pilot is not loaded")
        return
    await data.async_analyze(hass)
    connection.send_result(msg["id"], await _suggestions_payload(hass, data))
