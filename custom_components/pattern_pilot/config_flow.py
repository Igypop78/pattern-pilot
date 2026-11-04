"""Setup wizard and options for Pattern Pilot."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
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
    CONF_SENSITIVITY,
    DEFAULT_ANALYSIS_TIME,
    DEFAULT_DOMAINS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SENSITIVITY,
    DOMAIN,
    NAME,
    SENSITIVITIES,
)

# Optional keys per step – a missing key means "cleared" in options.
_OPTIONAL_KEYS = {
    "tracking": (CONF_AREAS, CONF_EXCLUDE_ENTITIES, CONF_EXCLUDE_USERS),
    "analysis": (),
}


def _suggest(value: Any) -> dict[str, Any]:
    return {"suggested_value": value}


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
            vol.Required(
                CONF_SENSITIVITY, default=o.get(CONF_SENSITIVITY, DEFAULT_SENSITIVITY)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=SENSITIVITIES,
                    translation_key="sensitivity",
                    mode=SelectSelectorMode.LIST,
                )
            ),
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


def _merge(options: dict[str, Any], step: str, user_input: dict[str, Any]) -> dict[str, Any]:
    new = {**options, **user_input}
    for key in _OPTIONAL_KEYS[step]:
        if key not in user_input:
            new.pop(key, None)
    return new


# --- config flow -----------------------------------------------------------------------


class PatternPilotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard: welcome → what to watch → done."""

    VERSION = 2

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
            return self.async_create_entry(title=NAME, data={}, options=self._options)
        return self.async_show_form(
            step_id="tracking", data_schema=_schema_tracking(self._users, self._options)
        )


class PatternPilotOptionsFlow(OptionsFlow):
    """Configure = menu of the same wizard parts."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["tracking", "analysis"]
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

    async def async_step_analysis(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save("analysis", user_input)
        return self.async_show_form(
            step_id="analysis", data_schema=_schema_analysis(dict(self.config_entry.options))
        )
