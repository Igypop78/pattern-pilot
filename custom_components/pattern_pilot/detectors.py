"""Universal change detection – turns sensor values into household events.

Pure Python, no Home Assistant imports, so it can be unit tested alone.

* ``ChangeDetector`` – any measured value (humidity, temperature, power,
  illuminance, CO₂ …). It learns the normal 10-minute variation of the
  sensor and reports a *rise* or *fall* that is clearly bigger.
* ``CounterRate`` – turns a counter (energy, water, gas) into a rate per
  hour, so the same ``ChangeDetector`` sees "consumption started / ended".
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

SIGNAL_RISE = "rise"
SIGNAL_RISE_END = "rise_end"
SIGNAL_FALL = "fall"
SIGNAL_FALL_END = "fall_end"

# multiplier of the learned normal variation (median of 10-minute ranges);
# the median stays robust even if real events happen while learning
SENSITIVITY_FACTOR = {"high": 3.0, "medium": 5.0, "low": 8.0}

# absolute minimum change per device class (in the unit after conversion)
FLOORS: dict[str, float] = {
    "humidity": 4.0,
    "moisture": 5.0,
    "temperature": 1.0,
    "power": 300.0,  # W
    "illuminance": 50.0,
    "carbon_dioxide": 150.0,
    "volatile_organic_compounds": 100.0,
    "volatile_organic_compounds_parts": 100.0,
    "pm25": 10.0,
    "pm10": 10.0,
    "sound_pressure": 10.0,
    "aqi": 15.0,
}
DEFAULT_FLOOR = 1e-6

LEARN_SECONDS = 24 * 3600  # learn the normal variation first
MIN_SAMPLES = 30
SAMPLE_EVERY = 60  # store a variation sample at most once a minute
MAX_SAMPLES = 1000
MAX_ACTIVE = 2 * 3600


@dataclass(slots=True)
class Signal:
    """A detected household event."""

    ts: float
    name: str
    value: float | None = None


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


class ChangeDetector:
    """Rise / fall detector with a learned, per-sensor threshold."""

    def __init__(
        self,
        floor: float = DEFAULT_FLOOR,
        sensitivity: str = "medium",
        window_s: float = 600,
        profile: dict[str, Any] | None = None,
    ) -> None:
        self.floor = floor
        self.factor = SENSITIVITY_FACTOR.get(sensitivity, SENSITIVITY_FACTOR["medium"])
        self.window_s = window_s
        self._window: deque[tuple[float, float]] = deque()
        self._ranges: deque[float] = deque(maxlen=MAX_SAMPLES)
        self._first_ts: float | None = None
        self._last_sample_ts = 0.0
        self._active: str | None = None  # "rise" / "fall"
        self._active_since = 0.0
        self._baseline = 0.0
        self._threshold_cache: float | None = None
        if profile:
            self._first_ts = profile.get("first_ts")
            self._ranges.extend(profile.get("ranges", [])[-MAX_SAMPLES:])

    # -- learning ------------------------------------------------------------------
    @property
    def learned(self) -> bool:
        return self._first_ts is not None and len(self._ranges) >= MIN_SAMPLES

    def is_ready(self, ts: float) -> bool:
        return (
            self.learned
            and self._first_ts is not None
            and ts - self._first_ts >= LEARN_SECONDS
        )

    @property
    def threshold(self) -> float:
        if self._threshold_cache is None:
            median = _percentile(list(self._ranges), 0.5)
            self._threshold_cache = max(self.floor, self.factor * median)
        return self._threshold_cache

    def profile(self) -> dict[str, Any]:
        return {"first_ts": self._first_ts, "ranges": [round(r, 4) for r in self._ranges]}

    # -- detection -----------------------------------------------------------------
    def update(self, ts: float, value: float) -> list[Signal]:
        if self._first_ts is None:
            self._first_ts = ts
        self._window.append((ts, value))
        while len(self._window) > 1 and ts - self._window[0][0] > self.window_s:
            self._window.popleft()
        low = min(v for _, v in self._window)
        high = max(v for _, v in self._window)

        out: list[Signal] = []
        if self._active is not None:
            out += self._check_end(ts, value)
        elif self.is_ready(ts):
            thr = self.threshold
            if value - low >= thr:
                self._start(ts, SIGNAL_RISE, low)
                out.append(Signal(ts, SIGNAL_RISE, round(value - low, 3)))
            elif high - value >= thr:
                self._start(ts, SIGNAL_FALL, high)
                out.append(Signal(ts, SIGNAL_FALL, round(high - value, 3)))

        # learn only from quiet periods (not during an event)
        if self._active is None and not out and ts - self._last_sample_ts >= SAMPLE_EVERY:
            self._ranges.append(high - low)
            self._last_sample_ts = ts
            self._threshold_cache = None
        return out

    def _start(self, ts: float, kind: str, baseline: float) -> None:
        self._active = kind
        self._active_since = ts
        self._baseline = baseline

    def _check_end(self, ts: float, value: float) -> list[Signal]:
        thr = self.threshold
        back = (
            value <= self._baseline + thr / 2
            if self._active == SIGNAL_RISE
            else value >= self._baseline - thr / 2
        )
        if not back and ts - self._active_since < MAX_ACTIVE:
            return []
        name = SIGNAL_RISE_END if self._active == SIGNAL_RISE else SIGNAL_FALL_END
        minutes = round((ts - self._active_since) / 60, 1)
        self._active = None
        self._window.clear()
        self._window.append((ts, value))
        return [Signal(ts, name, minutes)]


class CounterRate:
    """Counter (kWh, m³, L …) → rate per hour.

    Resets (daily counters, meter swaps) are ignored. When the counter does
    not move for ``idle_s`` the rate drops to 0 (``tick``).
    """

    def __init__(self, idle_s: float = 300) -> None:
        self.idle_s = idle_s
        self._last: tuple[float, float] | None = None
        self._last_rate = 0.0

    def update(self, ts: float, total: float) -> float | None:
        if self._last is None:
            self._last = (ts, total)
            return None
        last_ts, last_total = self._last
        self._last = (ts, total)
        delta = total - last_total
        dt = ts - last_ts
        if delta < 0 or dt <= 0:  # reset or clock issue
            return None
        rate = delta / dt * 3600
        self._last_rate = rate
        return rate

    def tick(self, ts: float) -> float | None:
        """Return 0 once when the counter has been idle long enough."""
        if self._last is None or self._last_rate == 0:
            return None
        if ts - self._last[0] >= self.idle_s:
            self._last_rate = 0.0
            return 0.0
        return None


# --- unit helpers --------------------------------------------------------------

_POWER_FACTORS = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0, "mW": 0.001}


def normalize(device_class: str | None, value: float, unit: str | None) -> float | None:
    """Convert to the unit the floors use (power → W)."""
    if device_class == "power":
        factor = _POWER_FACTORS.get(unit or "W")
        return None if factor is None else value * factor
    return value
