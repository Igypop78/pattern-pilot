"""Integration tests in a real Home Assistant (CI)."""

from datetime import date
import os
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


@pytest.fixture(autouse=True)
def fresh_database(hass: HomeAssistant):
    """Every test starts with an empty Pattern Pilot database."""
    for suffix in ("", "-wal", "-shm"):
        path = hass.config.path(DB_FILENAME + suffix)
        if os.path.exists(path):
            os.remove(path)
    yield


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
    assert not [r for r in rows if r["kind"] == "state" and r["entity_id"].startswith("sensor.")]

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
    signals = [(r["old"], r["new"]) for r in rows if r["kind"] == "signal" and r["entity_id"] == WATER]
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


async def test_overview_websocket(hass: HomeAssistant, hass_ws_client) -> None:
    entry = await _setup(hass)
    light = "light.kuchyna_linka"
    hass.states.async_set(light, "off")
    await hass.async_block_till_done()
    hass.states.async_set(light, "on", context=Context(user_id="igor"))
    hass.states.async_set(light, "off", context=Context())
    await hass.async_block_till_done()
    await entry.runtime_data.collector.async_flush()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "pattern_pilot/overview"})
    msg = await client.receive_json()
    assert msg["success"], msg
    res = msg["result"]
    assert res["status"] == "collecting"
    assert res["days_needed"] == 21
    assert len(res["hourly_today"]) == 24
    assert sum(res["hourly_today"]) == 2
    assert res["actors"] == {"human": 1, "physical": 1}
    assert res["top"][0]["entity_id"] == light
    assert res["top"][0]["count"] == 2
    assert res["recent"][0]["entity_id"] == light


async def test_card_is_served(hass: HomeAssistant, hass_client) -> None:
    await _setup(hass)
    client = await hass_client()
    resp = await client.get("/pattern_pilot/igy-pattern-pilot-card.js")
    assert resp.status == 200
    assert "igy-pattern-pilot-card" in await resp.text()


async def test_command_paired_with_late_confirmation(hass: HomeAssistant) -> None:
    """Zigbee2MQTT / MQTT: the state arrives later with a fresh context."""
    entry = await _setup(hass, domains=["light", "switch", "climate"])
    bulb = "light.zahrada_vchod_ziarovka_1"
    hass.states.async_set(bulb, "off")
    await hass.async_block_till_done()
    run_ctx = Context(parent_id="trigger")
    hass.bus.async_fire(
        "automation_triggered",
        {"entity_id": "automation.zahrada_vecer", "name": "x", "source": "sun"},
        context=run_ctx,
    )
    hass.bus.async_fire(
        "call_service",
        {"domain": "light", "service": "turn_on", "service_data": {"entity_id": [bulb]}},
        context=run_ctx,
    )
    await hass.async_block_till_done()
    hass.states.async_set(bulb, "on", context=Context())  # confirmation from MQTT
    # person in the app, confirmation again without context
    hass.bus.async_fire(
        "call_service",
        {"domain": "light", "service": "turn_off", "service_data": {"entity_id": bulb}},
        context=Context(user_id="igor"),
    )
    await hass.async_block_till_done()
    hass.states.async_set(bulb, "off", context=Context())
    await hass.async_block_till_done()

    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == bulb]
    assert [(r["new"], r["actor"]) for r in rows] == [("on", "automation"), ("off", "human")]
    assert rows[0]["ref"] == "automation.zahrada_vecer"


async def test_pulse_counted_once(hass: HomeAssistant) -> None:
    """Gate opened by another app directly on the Shelly: on → off after 1 s."""
    entry = await _setup(hass, domains=["light", "switch", "climate"])
    gate = "switch.brana"
    hass.states.async_set(gate, "off")
    await hass.async_block_till_done()
    hass.states.async_set(gate, "on", context=Context())
    hass.states.async_set(gate, "off", context=Context())
    await hass.async_block_till_done()
    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == gate]
    assert [(r["new"], r["actor"]) for r in rows] == [("on", "physical")]


async def test_pulse_from_ha_command(hass: HomeAssistant) -> None:
    entry = await _setup(hass, domains=["light", "switch", "climate"])
    gate = "switch.brana"
    hass.states.async_set(gate, "off")
    await hass.async_block_till_done()
    hass.bus.async_fire(
        "call_service",
        {"domain": "switch", "service": "turn_on", "service_data": {"entity_id": gate}},
        context=Context(user_id="igor"),
    )
    await hass.async_block_till_done()
    hass.states.async_set(gate, "on", context=Context())
    hass.states.async_set(gate, "off", context=Context())  # Shelly timer
    await hass.async_block_till_done()
    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == gate]
    assert [(r["new"], r["actor"]) for r in rows] == [("on", "human")]


async def test_thermostat_own_program_is_device(hass: HomeAssistant) -> None:
    entry = await _setup(hass, domains=["light", "switch", "climate"])
    trv = "climate.pracovna_termostat"
    hass.states.async_set(trv, "heat", {"temperature": 20})
    await hass.async_block_till_done()
    hass.states.async_set(trv, "heat", {"temperature": 17}, context=Context())
    await hass.async_block_till_done()
    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == trv]
    assert [(r["kind"], r["actor"]) for r in rows] == [("attr", "device")]


async def test_area_target_resolved(hass: HomeAssistant) -> None:
    from homeassistant.helpers import area_registry as ar, entity_registry as er

    entry = await _setup(hass, domains=["light"])
    area = ar.async_get(hass).async_create("Záhrada")
    ent = er.async_get(hass).async_get_or_create("light", "test", "bulb2", suggested_object_id="zahrada_bulb")
    er.async_get(hass).async_update_entity(ent.entity_id, area_id=area.id)
    hass.states.async_set(ent.entity_id, "off")
    await hass.async_block_till_done()
    hass.bus.async_fire(
        "call_service",
        {"domain": "light", "service": "turn_on", "service_data": {"area_id": area.id}},
        context=Context(user_id="igor"),
    )
    await hass.async_block_till_done()
    hass.states.async_set(ent.entity_id, "on", context=Context())
    await hass.async_block_till_done()
    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == ent.entity_id]
    assert [(r["new"], r["actor"]) for r in rows] == [("on", "human")]


async def test_zigbee2mqtt_group_members(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    entry = await _setup(hass, domains=["light"])
    mqtt_entry = MockConfigEntry(domain="mqtt", data={})
    mqtt_entry.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    devices = {
        name: dev_reg.async_get_or_create(
            config_entry_id=mqtt_entry.entry_id, identifiers={("mqtt", ident)}, name=name
        )
        for name, ident in (
            ("bulb1", "zigbee2mqtt_0xAAA1"),
            ("bulb2", "zigbee2mqtt_0xaaa2"),
            ("group", "zigbee2mqtt_1221051039810110150109113116116_7"),
        )
    }
    ids = {
        name: ent_reg.async_get_or_create(
            "light", "mqtt", f"u_{name}", device_id=dev.id, suggested_object_id=f"zahrada_{name}"
        ).entity_id
        for name, dev in devices.items()
    }
    collector = entry.runtime_data.collector
    collector.groups.set_z2m_groups(
        "zigbee2mqtt",
        [{"id": 7, "friendly_name": "Záhrada vchod", "members": [
            {"ieee_address": "0xaaa1", "endpoint": 1}, {"ieee_address": "0xAAA2", "endpoint": 1}]}],
    )
    assert collector.groups.expand(ids["group"]) == {ids["bulb1"], ids["bulb2"]}

    for name in ("bulb1", "bulb2"):
        hass.states.async_set(ids[name], "off")
    await hass.async_block_till_done()
    run_ctx = Context(parent_id="trigger")
    hass.bus.async_fire(
        "automation_triggered",
        {"entity_id": "automation.zahrada_vchod_pohyb", "name": "x", "source": "motion"},
        context=run_ctx,
    )
    hass.bus.async_fire(
        "call_service",
        {"domain": "light", "service": "turn_on", "service_data": {"entity_id": ids["group"]}},
        context=run_ctx,
    )
    await hass.async_block_till_done()
    for name in ("bulb1", "bulb2"):
        hass.states.async_set(ids[name], "on", context=Context())  # members report via MQTT
    await hass.async_block_till_done()
    rows = await _rows(hass, entry)
    bulbs = [(r["entity_id"], r["actor"]) for r in rows if r["entity_id"] in (ids["bulb1"], ids["bulb2"])]
    assert bulbs == [(ids["bulb1"], "automation"), (ids["bulb2"], "automation")]


async def test_ha_group_members(hass: HomeAssistant) -> None:
    entry = await _setup(hass, domains=["light"])
    hass.states.async_set("light.skupina", "off", {"entity_id": ["light.a", "light.b"]})
    hass.states.async_set("light.a", "off")
    await hass.async_block_till_done()
    hass.bus.async_fire(
        "call_service",
        {"domain": "light", "service": "turn_on", "service_data": {"entity_id": "light.skupina"}},
        context=Context(user_id="igor"),
    )
    await hass.async_block_till_done()
    hass.states.async_set("light.a", "on", context=Context())
    await hass.async_block_till_done()
    rows = [r for r in await _rows(hass, entry) if r["entity_id"] == "light.a"]
    assert [(r["new"], r["actor"]) for r in rows] == [("on", "human")]
