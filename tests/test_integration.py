"""Integration tests in a real Home Assistant (CI)."""

from datetime import date
import time

import pytest

from homeassistant import config_entries
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pattern_pilot.const import (
    CONF_DOMAINS,
    CONF_EXCLUDE_USERS,
    DB_FILENAME,
    DOMAIN,
)
from custom_components.pattern_pilot.store import EventStore

HUMIDITY = "sensor.kupelna_dole_vlhkost"
WATER = "sensor.vodomer"


def _learned_profile() -> dict:
    return {"first_ts": time.time() - 3 * 86400, "ranges": [0.5] * 200}


async def _seed_profiles(hass: HomeAssistant, profiles: dict) -> None:
    store = EventStore(hass.config.path(DB_FILENAME))

    def seed() -> None:
        store.open()
        store.save_profiles(profiles)
        store.close()

    await hass.async_add_executor_job(seed)


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    opts = {
        CONF_DOMAINS: ["light", "binary_sensor", "person", "sensor"],
        CONF_EXCLUDE_USERS: ["nodered"],
        **options,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options=opts, title="Pattern Pilot", version=2
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _rows(hass: HomeAssistant, entry: MockConfigEntry) -> list[dict]:
    data = entry.runtime_data
    await data.collector.async_flush()
    return list(reversed(await hass.async_add_executor_job(data.store.recent, 200)))


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"history_days": 120, "analysis_time": "03:45:00", "sensitivity": "medium"},
    )
    assert result["step_id"] == "tracking"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"domains": ["light", "binary_sensor", "sensor"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["sensitivity"] == "medium"
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pattern_pilot_status") is not None


async def test_options_menu(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["tracking", "analysis"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "analysis"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"history_days": 90, "analysis_time": "04:00:00", "sensitivity": "high"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["history_days"] == 90
    assert entry.options[CONF_EXCLUDE_USERS] == ["nodered"]


async def test_migration_from_v1(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        version=1,
        options={
            "domains": ["light", "person"],
            "humidity_sensors": [HUMIDITY],
            "humidity_rise": 8,
            "workday_sensor": "binary_sensor.workday",
            "history_days": 120,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.options == {"domains": ["light", "person", "sensor"], "history_days": 120}


async def test_attribution(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    light = "light.kupelna_dole"
    hass.states.async_set(light, "off")
    hass.states.async_set("switch.ignored", "off")
    await hass.async_block_till_done()

    hass.states.async_set(light, "on", {"brightness": 200}, context=Context(user_id="igor"))
    hass.states.async_set(light, "off", context=Context())
    run_ctx = Context(parent_id="trigger")
    hass.bus.async_fire(
        "automation_triggered",
        {"entity_id": "automation.kupelna_svetlo", "name": "x", "source": "motion"},
        context=run_ctx,
    )
    await hass.async_block_till_done()
    hass.states.async_set(light, "on", context=run_ctx)
    hass.states.async_set(light, "off", context=Context(user_id="igor"))
    hass.states.async_set(light, "on", context=Context(user_id="nodered"))
    hass.states.async_set(light, "on", {"brightness": 60}, context=Context(user_id="igor"))
    hass.states.async_set("switch.ignored", "on", context=Context(user_id="igor"))
    await hass.async_block_till_done()

    rows = await _rows(hass, entry)
    light_rows = [r for r in rows if r["entity_id"] == light]
    assert [(r["kind"], r["new"], r["actor"]) for r in light_rows] == [
        ("state", "on", "human"),
        ("state", "off", "physical"),
        ("state", "on", "automation"),
        ("state", "off", "human"),
        ("state", "on", "external"),
        ("attr", "brightness:60", "human"),
    ]
    assert light_rows[2]["ref"] == "automation.kupelna_svetlo"
    assert light_rows[3]["override"] == 1
    assert [r for r in rows if r["kind"] == "run"][0]["actor"] == "automation"
    assert not [r for r in rows if r["entity_id"] == "switch.ignored"]

    store = entry.runtime_data.store
    ctx = await hass.async_add_executor_job(
        lambda: store.conn.execute(
            "SELECT day_type, people_home FROM context"
        ).fetchall()
    )
    assert len(ctx) == 4
    assert ctx[0][0] in ("workday", "weekend", "holiday")


async def test_any_sensor_rise_with_learned_profile(hass: HomeAssistant) -> None:
    await _seed_profiles(hass, {HUMIDITY: _learned_profile()})
    entry = await _setup(hass)
    attrs = {"unit_of_measurement": "%", "device_class": "humidity", "state_class": "measurement"}
    hass.states.async_set(HUMIDITY, "55", attrs)
    await hass.async_block_till_done()
    for value in ("55", "56", "62", "70", "74"):
        hass.states.async_set(HUMIDITY, value, attrs)
        await hass.async_block_till_done()
    # not a measured sensor class → ignored
    hass.states.async_set("sensor.menic_napatie", "230", {"device_class": "voltage", "state_class": "measurement"})
    hass.states.async_set("sensor.menic_napatie", "250", {"device_class": "voltage", "state_class": "measurement"})
    await hass.async_block_till_done()

    rows = await _rows(hass, entry)
    signals = [(r["entity_id"], r["old"], r["new"]) for r in rows if r["kind"] == "signal"]
    assert signals == [(HUMIDITY, "humidity", "rise")]
    assert not [r for r in rows if r["kind"] == "state" and r["domain"] == "sensor"]

    collector = entry.runtime_data.collector
    assert collector.describe()["sensors_ready"] == 1
    status = hass.states.get("sensor.pattern_pilot_status")
    assert status.state == "collecting"


async def test_energy_counter(hass: HomeAssistant) -> None:
    await _seed_profiles(hass, {WATER: {"first_ts": time.time() - 3 * 86400, "ranges": [0.0] * 200}})
    entry = await _setup(hass)
    collector = entry.runtime_data.collector
    collector.counters = {WATER}  # normally read from the Energy dashboard
    collector._sensor_kind.clear()
    attrs = {"unit_of_measurement": "m³", "device_class": "water", "state_class": "total_increasing"}
    hass.states.async_set(WATER, "100.000", attrs)
    await hass.async_block_till_done()
    for idle in (1, 2):  # meter reports the same value = no flow
        hass.states.async_set(WATER, "100.000", {**attrs, "seq": idle})
        await hass.async_block_till_done()
    for value in ("100.002", "100.004", "100.006"):
        hass.states.async_set(WATER, value, attrs)
        await hass.async_block_till_done()
    rows = await _rows(hass, entry)
    signals = [(r["old"], r["new"]) for r in rows if r["kind"] == "signal"]
    assert signals[:1] == [("counter", "rise")]


async def test_holidays(hass: HomeAssistant) -> None:
    pytest.importorskip("holidays")
    hass.config.country = "SK"
    entry = await _setup(hass)
    ctx = entry.runtime_data.collector.context
    assert ctx.day_type(date(2026, 1, 1)) == "holiday"
    assert ctx.day_type(date(2026, 11, 7)) == "weekend"
    assert ctx.day_type(date(2026, 11, 4)) == "workday"


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
