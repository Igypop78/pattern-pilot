"""Signal detectors – turn raw sensor values into household events.

Pure Python, no Home Assistant imports, so they can be unit tested alone.
Every detector gets ``update(ts, value)`` (ts = epoch seconds, value already
converted to the detector unit) and returns a list of ``Signal``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .const import (
    SIGNAL_LOAD_END,
    SIGNAL_LOAD_START,
    SIGNAL_SHOWER_END,
    SIGNAL_SHOWER_START,
    SIGNAL_WATER_USE,
)


@dataclass(slots=True)
class Signal:
    """A detected household event."""

    ts: float
    name: str
    value: float | None = None


class HumidityRiseDetector:
    """Shower / bath: humidity rises fast, later falls back.

    Start: value - min(last ``window_s``) >= ``rise``.
    End: value falls to baseline + rise/2, or after ``max_duration_s``.
    """

    def __init__(
        self,
        rise: float = 8.0,
        window_s: float = 600,
        max_duration_s: float = 7200,
    ) -> None:
        self.rise = rise
        self.window_s = window_s
        self.max_duration_s = max_duration_s
        self._samples: deque[tuple[float, float]] = deque()
        self._active_since: float | None = None
        self._baseline = 0.0

    @property
    def active(self) -> bool:
        return self._active_since is not None

    def update(self, ts: float, value: float) -> list[Signal]:
        out: list[Signal] = []
        if self._active_since is not None:
            if (
                value <= self._baseline + self.rise / 2
                or ts - self._active_since >= self.max_duration_s
            ):
                minutes = round((ts - self._active_since) / 60, 1)
                out.append(Signal(ts, SIGNAL_SHOWER_END, minutes))
                self._active_since = None
                self._samples.clear()
            self._samples.append((ts, value))
            return out

        self._samples.append((ts, value))
        while self._samples and ts - self._samples[0][0] > self.window_s:
            self._samples.popleft()
        low = min(v for _, v in self._samples)
        if value - low >= self.rise:
            self._baseline = low
            self._active_since = ts
            out.append(Signal(ts, SIGNAL_SHOWER_START, round(value - low, 1)))
        return out


class PowerStepDetector:
    """Appliance switched on: consumption jumps by ``step`` W above baseline.

    Baseline = minimum of the last ``window_s`` before the jump.
    End: value falls below baseline + step/2 (or after ``max_duration_s``).
    """

    def __init__(
        self,
        step: float = 1500.0,
        window_s: float = 300,
        max_duration_s: float = 4 * 3600,
    ) -> None:
        self.step = step
        self.window_s = window_s
        self.max_duration_s = max_duration_s
        self._samples: deque[tuple[float, float]] = deque()
        self._active_since: float | None = None
        self._baseline = 0.0

    @property
    def active(self) -> bool:
        return self._active_since is not None

    def update(self, ts: float, value: float) -> list[Signal]:
        out: list[Signal] = []
        if self._active_since is not None:
            if (
                value < self._baseline + self.step / 2
                or ts - self._active_since >= self.max_duration_s
            ):
                minutes = round((ts - self._active_since) / 60, 1)
                out.append(Signal(ts, SIGNAL_LOAD_END, minutes))
                self._active_since = None
                self._samples.clear()
                self._samples.append((ts, value))
            return out

        while self._samples and ts - self._samples[0][0] > self.window_s:
            self._samples.popleft()
        if self._samples:
            low = min(v for _, v in self._samples)
            if value - low >= self.step:
                self._baseline = low
                self._active_since = ts
                out.append(Signal(ts, SIGNAL_LOAD_START, round(value - low)))
        self._samples.append((ts, value))
        return out


class WaterUseDetector:
    """Water drawn: groups meter increases (or flow) into one usage.

    Works with a total meter (litres, increasing) or with a flow sensor
    (litres/min). A usage ends after ``gap_s`` without consumption; the
    caller must call ``tick(ts)`` periodically (or when a timer fires).
    One ``water_use`` signal is produced at the end, timestamped with the
    start of the usage, if at least ``min_litres`` were used.
    """

    def __init__(self, min_litres: float = 3.0, gap_s: float = 180, flow: bool = False) -> None:
        self.min_litres = min_litres
        self.gap_s = gap_s
        self.flow = flow
        self._last_total: float | None = None
        self._last_flow_ts: float | None = None
        self._last_flow: float = 0.0
        self._start: float | None = None
        self._last_use: float = 0.0
        self._litres = 0.0

    @property
    def active(self) -> bool:
        return self._start is not None

    def _use(self, ts: float, litres: float) -> None:
        if litres <= 0:
            return
        if self._start is None:
            self._start = ts
            self._litres = 0.0
        self._litres += litres
        self._last_use = ts

    def update(self, ts: float, value: float) -> list[Signal]:
        out = self.tick(ts)
        if self.flow:
            # integrate previous flow (l/min) over elapsed time
            if self._last_flow_ts is not None and self._last_flow > 0:
                self._use(ts, self._last_flow * (ts - self._last_flow_ts) / 60)
            if value > 0 and self._start is None:
                self._start = ts
                self._litres = 0.0
            if value > 0:
                self._last_use = ts
            self._last_flow_ts = ts
            self._last_flow = value
            return out
        if self._last_total is not None:
            delta = value - self._last_total
            if 0 < delta < 1000:  # ignore meter resets / jumps
                self._use(ts, delta)
        self._last_total = value
        return out

    def tick(self, ts: float) -> list[Signal]:
        """Close the usage when nothing was used for ``gap_s``."""
        if self._start is None:
            return []
        if self.flow and self._last_flow > 0:
            return []
        if ts - self._last_use < self.gap_s:
            return []
        start, litres = self._start, self._litres
        self._start = None
        self._litres = 0.0
        if litres >= self.min_litres:
            return [Signal(start, SIGNAL_WATER_USE, round(litres, 1))]
        return []


# --- unit helpers --------------------------------------------------------------

_POWER_FACTORS = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0, "mW": 0.001}
_VOLUME_FACTORS = {
    "L": 1.0,
    "l": 1.0,
    "m³": 1000.0,
    "m3": 1000.0,
    "gal": 3.78541,
    "ft³": 28.3168,
    "CCF": 2831.68,
    "mL": 0.001,
}
_FLOW_FACTORS = {  # -> l/min
    "L/min": 1.0,
    "l/min": 1.0,
    "L/h": 1 / 60,
    "m³/h": 1000 / 60,
    "m³/min": 1000.0,
    "m³/s": 60000.0,
    "gal/min": 3.78541,
    "ft³/min": 28.3168,
    "mL/s": 0.06,
}


def to_watts(value: float, unit: str | None) -> float | None:
    factor = _POWER_FACTORS.get(unit or "W")
    return None if factor is None else value * factor


def to_litres(value: float, unit: str | None) -> float | None:
    factor = _VOLUME_FACTORS.get(unit or "L")
    return None if factor is None else value * factor


def to_litres_per_min(value: float, unit: str | None) -> float | None:
    factor = _FLOW_FACTORS.get(unit or "L/min")
    return None if factor is None else value * factor


def is_flow_unit(unit: str | None) -> bool:
    return unit in _FLOW_FACTORS
