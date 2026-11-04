"""Setup wizard and options for Pattern Pilot."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_ANALYSIS_TIME,
    CONF_AREAS,
    CONF_DOMAINS,
    CONF_EXCLUDE_ENTITIES,
    CONF_EXCLUDE_USERS,
    CONF_HISTORY_DAYS,
    CONF_HUMIDITY_RISE,
    CONF_HUMIDITY_SENSORS,
    CONF_LUX_SENSOR,
    CONF_POWER_SENSORS,
    CONF_POWER_STEP,
    CONF_TEMP_SENSOR,
    CONF_WATER_MIN,
    CONF_WATER_SENSORS,
    CONF_WORKDAY_SENSOR,
    DEFAULT_ANALYSIS_TIME,
    DEFAULT_DOMAINS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_HUMIDITY_RISE,
    DEFAULT_POWER_STEP,
    DEFAULT_WATER_MIN,
    DOMAIN,
    NAME,
)

# Words that mark a bathroom (area name or id) – used for suggestions only.
_BATH_WORDS = ("bath", "kupel", "kúpeľ", "koupel", "bad", "łazien", "wc", "sprch", "shower")

# Optional keys per step – a missing key means "cleared" in options.
_OPTIONAL_KEYS = {
    "tracking": (CONF_AREAS, CONF_EXCLUDE_ENTITIES, CONF_EXCLUDE_USERS),
    "signals": (CONF_HUMIDITY_SENSORS, CONF_POWER_SENSORS, CONF_WATER_SENSORS),
    "context": (CONF_WORKDAY_SENSOR, CONF_LUX_SENSOR, CONF_TEMP_SENSOR),
    "analysis": (),
}


def _suggest(value: Any) -> dict[str, Any]:
    return {"suggested_value": value}


# --- suggestions -----------------------------------------------------------------


def _suggest_humidity(hass: HomeAssistant) -> list[str]:
    ent_reg = er.async_get(hass)
    area_reg = ar.async_get(hass)
    dev_reg = dr.async_get(hass)
    found: list[str] = []
    for state in hass.states.async_all("sensor"):
        if state.attributes.get("device_class") != "humidity":
            continue
        entry = ent_reg.async_get(state.entity_id)
        area_id = None
        if entry:
            if entry.entity_category is not None:
                continue
            area_id = entry.area_id
            if area_id is None and entry.device_id and (dev := dev_reg.async_get(entry.device_id)):
                area_id = dev.area_id
        names = [state.entity_id, str(state.attributes.get("friendly_name", ""))]
        if area_id and (area := area_reg.async_get_area(area_id)):
            names += [area.id, area.name]
        text = " ".join(names).lower()
        if any(word in text for word in _BATH_WORDS):
            found.append(state.entity_id)
    return found


def _suggest_workday(hass: HomeAssistant) -> str | None:
    for entry in er.async_get(hass).entities.values():
        if entry.platform == "workday" and entry.domain == "binary_sensor" and not entry.disabled:
            return entry.entity_id
    return None


async def _load_users(hass: HomeAssistant) -> list[SelectOptionDict]:
    users = await hass.auth.async_get_users()
    return [
        SelectOptionDict(value=u.id, label=u.name or u.id)
        for u in users
        if not u.system_generated
    ]


# --- schemas -------------------------------------------------------------------------


def _schema_analysis(o: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_HISTORY_DAYS, default=o.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=30, max=365, step=1, unit_of_measurement="d", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_ANALYSIS_TIME, default=o.get(CONF_ANALYSIS_TIME, DEFAULT_ANALYSIS_TIME)
            ): TimeSelector(),
        }
    )


def _schema_tracking(users: list[SelectOptionDict], o: dict[str, Any]) -> vol.Schema:
    domains = sorted(set(DEFAULT_DOMAINS) | set(o.get(CONF_DOMAINS) or []))
    return vol.Schema(
        {
            vol.Required(
                CONF_DOMAINS, default=o.get(CONF_DOMAINS) or list(DEFAULT_DOMAINS)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=domains,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            ),
            vol.Optional(CONF_AREAS, description=_suggest(o.get(CONF_AREAS))): AreaSelector(
                AreaSelectorConfig(multiple=True)
            ),
            vol.Optional(
                CONF_EXCLUDE_ENTITIES, description=_suggest(o.get(CONF_EXCLUDE_ENTITIES))
            ): EntitySelector(EntitySelectorConfig(multiple=True)),
            vol.Optional(
                CONF_EXCLUDE_USERS, description=_suggest(o.get(CONF_EXCLUDE_USERS))
            ): SelectSelector(
                SelectSelectorConfig(
                    options=users, multiple=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
        }
    )


def _schema_signals(o: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_HUMIDITY_SENSORS, description=_suggest(o.get(CONF_HUMIDITY_SENSORS))
            ): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="humidity", multiple=True)
            ),
            vol.Required(
                CONF_HUMIDITY_RISE, default=o.get(CONF_HUMIDITY_RISE, DEFAULT_HUMIDITY_RISE)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=3, max=30, step=0.5, unit_of_measurement="%", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_POWER_SENSORS, description=_suggest(o.get(CONF_POWER_SENSORS))
            ): EntitySelector(
                EntitySelectorConfig(domain="sensor", device_class="power", multiple=True)
            ),
            vol.Required(
                CONF_POWER_STEP, default=o.get(CONF_POWER_STEP, DEFAULT_POWER_STEP)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=200, max=10000, step=100, unit_of_measurement="W", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_WATER_SENSORS, description=_suggest(o.get(CONF_WATER_SENSORS))
            ): EntitySelector(
                EntitySelectorConfig(
                    domain="sensor", device_class=["water", "volume_flow_rate"], multiple=True
                )
            ),
            vol.Required(
                CONF_WATER_MIN, default=o.get(CONF_WATER_MIN, DEFAULT_WATER_MIN)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.5, max=100, step=0.5, unit_of_measurement="L", mode=NumberSelectorMode.BOX
                )
            ),
        }
    )


def _schema_context(o: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_WORKDAY_SENSOR, description=_suggest(o.get(CONF_WORKDAY_SENSOR))
            ): EntitySelector(EntitySelectorConfig(domain="binary_sensor")),
            vol.Optional(
                CONF_LUX_SENSOR, description=_suggest(o.get(CONF_LUX_SENSOR))
            ): EntitySelector(EntitySelectorConfig(domain="sensor", device_class="illuminance")),
            vol.Optional(
                CONF_TEMP_SENSOR, description=_suggest(o.get(CONF_TEMP_SENSOR))
            ): EntitySelector(EntitySelectorConfig(domain=["sensor", "weather"])),
        }
    )


def _merge(options: dict[str, Any], step: str, user_input: dict[str, Any]) -> dict[str, Any]:
    new = {**options, **user_input}
    for key in _OPTIONAL_KEYS[step]:
        if key not in user_input:
            new.pop(key, None)
    return new


# --- config flow -----------------------------------------------------------------------


class PatternPilotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard: welcome → tracking → signals → context → done."""

    VERSION = 1

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}
        self._users: list[SelectOptionDict] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> PatternPilotOptionsFlow:
        return PatternPilotOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            self._options = _merge(self._options, "analysis", user_input)
            self._users = await _load_users(self.hass)
            return await self.async_step_tracking()
        return self.async_show_form(step_id="user", data_schema=_schema_analysis(self._options))

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._options = _merge(self._options, "tracking", user_input)
            if CONF_HUMIDITY_SENSORS not in self._options:
                self._options[CONF_HUMIDITY_SENSORS] = _suggest_humidity(self.hass)
            return await self.async_step_signals()
        return self.async_show_form(
            step_id="tracking", data_schema=_schema_tracking(self._users, self._options)
        )

    async def async_step_signals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._options = _merge(self._options, "signals", user_input)
            if CONF_WORKDAY_SENSOR not in self._options and (wd := _suggest_workday(self.hass)):
                self._options[CONF_WORKDAY_SENSOR] = wd
            return await self.async_step_context()
        return self.async_show_form(step_id="signals", data_schema=_schema_signals(self._options))

    async def async_step_context(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._options = _merge(self._options, "context", user_input)
            return self.async_create_entry(title=NAME, data={}, options=self._options)
        return self.async_show_form(step_id="context", data_schema=_schema_context(self._options))


class PatternPilotOptionsFlow(OptionsFlow):
    """Configure = menu of the same wizard parts."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["tracking", "signals", "context", "analysis"]
        )

    def _save(self, step: str, user_input: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(
            data=_merge(dict(self.config_entry.options), step, user_input)
        )

    async def async_step_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save("tracking", user_input)
        users = await _load_users(self.hass)
        return self.async_show_form(
            step_id="tracking",
            data_schema=_schema_tracking(users, dict(self.config_entry.options)),
        )

    async def async_step_signals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save("signals", user_input)
        return self.async_show_form(
            step_id="signals", data_schema=_schema_signals(dict(self.config_entry.options))
        )

    async def async_step_context(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save("context", user_input)
        return self.async_show_form(
            step_id="context", data_schema=_schema_context(dict(self.config_entry.options))
        )

    async def async_step_analysis(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save("analysis", user_input)
        return self.async_show_form(
            step_id="analysis", data_schema=_schema_analysis(dict(self.config_entry.options))
        )
