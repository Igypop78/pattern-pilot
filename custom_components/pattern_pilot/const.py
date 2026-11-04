"""Constants for Pattern Pilot."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pattern_pilot"
NAME: Final = "Pattern Pilot"
VERSION: Final = "0.1.2"

DB_FILENAME: Final = "pattern_pilot.db"
SCHEMA_VERSION: Final = 2

# --- options keys -----------------------------------------------------------
CONF_AREAS: Final = "areas"
CONF_DOMAINS: Final = "domains"
CONF_EXCLUDE_ENTITIES: Final = "exclude_entities"
CONF_EXCLUDE_USERS: Final = "exclude_users"
CONF_SENSITIVITY: Final = "sensitivity"
CONF_HISTORY_DAYS: Final = "history_days"
CONF_ANALYSIS_TIME: Final = "analysis_time"

DEFAULT_HISTORY_DAYS: Final = 120
DEFAULT_ANALYSIS_TIME: Final = "03:45:00"
DEFAULT_SENSITIVITY: Final = "medium"
SENSITIVITIES: Final = ["low", "medium", "high"]

# Options of v0.1.0 that are no longer used (removed by migration).
REMOVED_OPTIONS: Final = (
    "humidity_sensors",
    "humidity_rise",
    "power_sensors",
    "power_step",
    "water_sensors",
    "water_min",
    "workday_sensor",
    "lux_sensor",
    "temperature_sensor",
)

# Days of data before suggestions make sense.
MIN_DAYS_FOR_ANALYSIS: Final = 21

# Domains where a person does something (actions).
ACTION_DOMAINS: Final = (
    "light",
    "switch",
    "cover",
    "fan",
    "climate",
    "media_player",
    "lock",
    "vacuum",
    "humidifier",
    "water_heater",
    "valve",
    "siren",
    "alarm_control_panel",
    "input_boolean",
    "input_select",
    "input_number",
    "input_button",
    "button",
    "select",
    "number",
    "scene",
    "script",
)

# Domains that are only signals (what happens in the house).
# "sensor" = numeric sensors → rise / fall events (raw values are not stored).
SIGNAL_DOMAINS: Final = (
    "binary_sensor",
    "person",
    "event",
    "sensor",
)

# Measured values worth watching (rise / fall says something about people).
MEASURE_DEVICE_CLASSES: Final = (
    "humidity",
    "moisture",
    "temperature",
    "power",
    "illuminance",
    "carbon_dioxide",
    "volatile_organic_compounds",
    "volatile_organic_compounds_parts",
    "pm25",
    "pm10",
    "aqi",
    "sound_pressure",
    "volume_flow_rate",
)

DEFAULT_DOMAINS: Final = [*ACTION_DOMAINS, *SIGNAL_DOMAINS]

# Attributes that matter when the state itself does not change.
TRACKED_ATTRIBUTES: Final = {
    "light": ("brightness",),
    "climate": ("temperature", "target_temp_low", "target_temp_high", "preset_mode", "fan_mode"),
    "fan": ("percentage", "preset_mode"),
    "media_player": ("source",),
    "humidifier": ("humidity",),
    "water_heater": ("temperature",),
}

# Minimal change of a numeric attribute that is worth storing.
ATTRIBUTE_MIN_DELTA: Final = {
    "brightness": 25.0,  # of 255 (~10 %)
    "percentage": 10.0,
}

# Who caused a change.
ACTOR_HUMAN: Final = "human"  # app, dashboard, voice (context.user_id)
ACTOR_PHYSICAL: Final = "physical"  # wall switch, device button (no context origin)
ACTOR_AUTOMATION: Final = "automation"  # automation or script
ACTOR_SYSTEM: Final = "system"  # some other integration (parent context, no user)
ACTOR_DEVICE: Final = "device"  # sensors reporting
ACTOR_EXTERNAL: Final = "external"  # excluded users (Node-RED, AppDaemon …)

MANUAL_ACTORS: Final = (ACTOR_HUMAN, ACTOR_PHYSICAL)

# Event kinds stored in the database.
KIND_STATE: Final = "state"
KIND_ATTRIBUTE: Final = "attr"
KIND_SIGNAL: Final = "signal"
KIND_RUN: Final = "run"
KIND_SERVICE: Final = "service"


# A person reverting what an automation did within this time = override.
OVERRIDE_WINDOW_S: Final = 120

FLUSH_INTERVAL_S: Final = 30

SIGNAL_STATS_UPDATED: Final = f"{DOMAIN}_stats_updated"
