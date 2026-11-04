"""Integration tests in a real Home Assistant (CI)."""

from homeassistant import config_entries
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pattern_pilot.const import (
    CONF_DOMAINS,
    CONF_EXCLUDE_USERS,
    CONF_HUMIDITY_SENSORS,
    DOMAIN,
)

HUMIDITY = "sensor.kupelna_dole_vlhkost"


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    opts = {
        CONF_DOMAINS: ["light", "binary_sensor", "person"],
        CONF_HUMIDITY_SENSORS: [HUMIDITY],
        CONF_EXCLUDE_USERS: ["nodered"],
        **options,
    }
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=opts, title="Pattern Pilot")
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
        result["flow_id"], {"history_days": 120, "analysis_time": "03:45:00"}
    )
    assert result["step_id"] == "tracking"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"domains": ["light", "binary_sensor"]}
    )
    assert result["step_id"] == "signals"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"humidity_rise": 8, "power_step": 1500, "water_min": 3}
    )
    assert result["step_id"] == "context"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["domains"] == ["light", "binary_sensor"]
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pattern_pilot_status") is not None


async def test_options_menu(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "analysis"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"history_days": 90, "analysis_time": "04:00:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["history_days"] == 90
    assert entry.options[CONF_HUMIDITY_SENSORS] == [HUMIDITY]


async def test_attribution(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    light = "light.kupelna_dole"
    hass.states.async_set(light, "off")
    hass.states.async_set("switch.ignored", "off")
    await hass.async_block_till_done()

    # 1. person in the app
    hass.states.async_set(light, "on", {"brightness": 200}, context=Context(user_id="igor"))
    # 2. wall switch (no context origin)
    hass.states.async_set(light, "off", context=Context())
    # 3. automation turns it on …
    run_ctx = Context(parent_id="trigger")
    hass.bus.async_fire(
        "automation_triggered",
        {"entity_id": "automation.kupelna_svetlo", "name": "x", "source": "state of binary_sensor.pohyb"},
        context=run_ctx,
    )
    await hass.async_block_till_done()
    hass.states.async_set(light, "on", context=run_ctx)
    # 4. … and the person turns it off right away = override
    hass.states.async_set(light, "off", context=Context(user_id="igor"))
    # 5. excluded user (Node-RED)
    hass.states.async_set(light, "on", context=Context(user_id="nodered"))
    # 6. brightness change only
    hass.states.async_set(light, "on", {"brightness": 60}, context=Context(user_id="igor"))
    # untracked domain
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
    assert light_rows[3]["ref"] == "automation.kupelna_svetlo"
    runs = [r for r in rows if r["kind"] == "run"]
    assert runs and runs[0]["actor"] == "automation"
    assert not [r for r in rows if r["entity_id"] == "switch.ignored"]

    # context snapshot only for manual actions
    store = entry.runtime_data.store
    n_ctx = await hass.async_add_executor_job(
        lambda: store.conn.execute("SELECT COUNT(*) FROM context").fetchone()[0]
    )
    assert n_ctx == 4


async def test_shower_signal_and_sensors(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    hass.states.async_set(HUMIDITY, "55", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    for value in ("56", "62", "70", "74"):
        hass.states.async_set(HUMIDITY, value, {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
    rows = await _rows(hass, entry)
    assert [r["new"] for r in rows if r["kind"] == "signal"] == ["shower_start"]
    # raw humidity values are never stored
    assert not [r for r in rows if r["kind"] == "state" and r["entity_id"] == HUMIDITY]

    status = hass.states.get("sensor.pattern_pilot_status")
    assert status.state == "collecting"
    assert status.attributes["days_needed"] == 21
    assert hass.states.get("sensor.pattern_pilot_database_size") is not None


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
