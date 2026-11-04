"""Automatic context – no sensors needed from the user.

* day type: workday / weekend / holiday (public holidays of the country set in HA)
* sun: day / night + elevation (sun.sun)
* outdoor temperature: from a weather entity found automatically
* people at home: person entities
"""

from __future__ import annotations

from datetime import date
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

_HOME_WORDS = ("home", "domov", "dom", "forecast_home")


def _load_holidays(country: str, years: list[int]) -> Any:
    import holidays  # noqa: PLC0415 - heavy import, executor only

    return holidays.country_holidays(country, years=years)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ContextProvider:
    """Builds the context snapshot stored with every manual action."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._holidays: Any = None
        self._years: set[int] = set()
        self.country: str | None = hass.config.country
        self.weather_entity: str | None = None

    async def async_prepare(self) -> None:
        """Load public holidays (this and next year) and find a weather entity."""
        self.country = self.hass.config.country
        year = dt_util.now().year
        if self.country and {year, year + 1} - self._years:
            try:
                self._holidays = await self.hass.async_add_executor_job(
                    _load_holidays, self.country, [year, year + 1]
                )
                self._years = {year, year + 1}
            except Exception as err:  # noqa: BLE001 - unknown country, missing library …
                _LOGGER.info("Pattern Pilot: holidays for %s not available (%s)", self.country, err)
                self._holidays = None
        self.weather_entity = self._find_weather()

    def _find_weather(self) -> str | None:
        ids = sorted(s.entity_id for s in self.hass.states.async_all("weather"))
        if not ids:
            return None
        for word in _HOME_WORDS:
            for entity_id in ids:
                if word in entity_id:
                    return entity_id
        return ids[0]

    def day_type(self, day: date) -> str:
        if self._holidays is not None and day in self._holidays:
            return "holiday"
        return "weekend" if day.weekday() >= 5 else "workday"

    def snapshot(self) -> dict[str, Any]:
        states = self.hass.states
        now = dt_util.now()
        sun = elevation = None
        if st := states.get("sun.sun"):
            sun = "day" if st.state == "above_horizon" else "night"
            elevation = _float(st.attributes.get("elevation"))
        temperature = None
        if self.weather_entity and (st := states.get(self.weather_entity)):
            temperature = _float(st.attributes.get("temperature"))
        people = sum(1 for p in states.async_all("person") if p.state == "home")
        return {
            "day_type": self.day_type(now.date()),
            "sun": sun,
            "sun_elevation": elevation,
            "temperature": temperature,
            "people_home": people,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "country": self.country,
            "holidays_loaded": sorted(self._years) if self._holidays is not None else None,
            "weather_entity": self.weather_entity,
        }
