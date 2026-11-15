"""Runs the analysis in Home Assistant and stores the suggestions."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .analysis import Analyzer, EntityInfo, Input, Manual, Override, Trig, build_automation
from .const import CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS, DOMAIN, SIGNAL_SUGGESTIONS_UPDATED

if TYPE_CHECKING:
    from . import PatternPilotData

_LOGGER = logging.getLogger(__name__)
NOTIFICATION_ID = f"{DOMAIN}_new_suggestions"


def _entity_info(hass: HomeAssistant, entity_id: str) -> EntityInfo:
    state = hass.states.get(entity_id)
    name = (state.attributes.get("friendly_name") if state else None) or entity_id
    device_class = state.attributes.get("device_class") if state else None
    area_name = None
    device_id = None
    entry = er.async_get(hass).async_get(entity_id)
    if entry:
        device_id = entry.device_id
        area_id = entry.area_id
        if area_id is None and entry.device_id and (dev := dr.async_get(hass).async_get(entry.device_id)):
            area_id = dev.area_id
        if area_id and (area := ar.async_get(hass).async_get_area(area_id)):
            area_name = area.name
    return EntityInfo(name=str(name), area=area_name, device_class=device_class, device_id=device_id)


async def async_run_analysis(hass: HomeAssistant, data: PatternPilotData, options: dict[str, Any]) -> int:
    """Analyse the recorded history; returns the number of new (undecided) suggestions."""
    collector = data.collector
    await collector.async_flush()
    first_ts = data.stats.first_ts
    if first_ts is None:
        return 0
    keep = int(options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))
    since = (dt_util.utcnow() - timedelta(days=keep)).timestamp()
    rows = await hass.async_add_executor_job(data.store.analysis_rows, since)

    entities: dict[str, EntityInfo] = {}
    exclude: set[str] = set()
    for row in rows["manual"] + rows["triggers"] + rows["automated"] + rows["overrides"]:
        eid = row[1]
        if eid not in entities:
            entities[eid] = _entity_info(hass, eid)
            if collector.is_ignored(eid):
                exclude.add(eid)
    groups = collector.group_map()
    for group in groups:
        if group not in entities:
            entities[group] = _entity_info(hass, group)

    inp = Input(
        manual=[Manual(*r) for r in rows["manual"]],
        triggers=[Trig(*r) for r in rows["triggers"]],
        automated=[Trig(*r) for r in rows["automated"]],
        overrides=[Override(*r) for r in rows["overrides"]],
        tz=ZoneInfo(hass.config.time_zone),
        now=dt_util.now(),
        first_ts=first_ts,
        day_type=collector.context.day_type,
        entities=entities,
        exclude=exclude | set(collector.exclude_entities),
        groups=groups,
    )
    results = await hass.async_add_executor_job(Analyzer(inp).run)

    lang = (hass.config.language or "en").split("-")[0]
    items = []
    for s in results:
        if s["kind"] == "improve":
            st = hass.states.get(s["automation"])
            if st is None:
                continue
            s["automation_config_id"] = st.attributes.get("id")
        else:
            for eid in s.get("entity_ids") or [s["entity_id"]]:
                if eid not in entities:
                    entities[eid] = _entity_info(hass, eid)
            trig = s.get("trigger_entity")
            trig_info = (entities.get(trig) or _entity_info(hass, trig)) if trig else None
            auto = build_automation(s, entities, trig_info, lang)
            if auto is None:
                continue
            s["automation"] = auto
        items.append(s)

    before = data.suggestions_new
    new = await hass.async_add_executor_job(data.store.save_suggestions, items)
    now = dt_util.now().isoformat()
    await hass.async_add_executor_job(data.store.meta_set, "last_analysis", now)
    data.suggestions_new = new
    data.last_analysis = now
    _LOGGER.debug("Pattern Pilot analysis: %s candidates, %s new", len(items), new)
    if new > before:
        _notify(hass, new, lang)
    async_dispatcher_send(hass, SIGNAL_SUGGESTIONS_UPDATED)
    return new


def _notify(hass: HomeAssistant, count: int, lang: str) -> None:
    from homeassistant.components import persistent_notification  # noqa: PLC0415

    if lang == "sk":
        title = "Pattern Pilot má nové návrhy"
        message = f"Počet návrhov automatizácií na posúdenie: {count}. Nájdeš ich v karte Igy Pattern Pilot."
    else:
        title = "Pattern Pilot has new suggestions"
        message = f"Automation suggestions to review: {count}. Open the Igy Pattern Pilot card."
    persistent_notification.async_create(hass, message, title, NOTIFICATION_ID)
