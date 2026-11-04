"""Detector tests (pure Python)."""

from custom_components.pattern_pilot.detectors import (
    LEARN_SECONDS,
    ChangeDetector,
    CounterRate,
    normalize,
)

DAY = LEARN_SECONDS


def _learned(floor=1e-6, sensitivity="medium", noise=0.5):
    """Detector that already learned a normal 10-min range of ``noise``."""
    return ChangeDetector(
        floor=floor,
        sensitivity=sensitivity,
        profile={"first_ts": 0.0, "ranges": [noise] * 200},
    )


def test_nothing_before_learning():
    det = ChangeDetector(floor=4)
    out = []
    for i, v in enumerate((50, 50, 70, 80)):
        out += det.update(i * 60.0, v)
    assert out == []


def test_learning_from_live_values():
    det = ChangeDetector(floor=1e-6)
    t = 0.0
    # one day of small noise, one sample per 2 minutes
    while t < DAY + 600:
        det.update(t, 50 + (0.3 if int(t / 120) % 2 else 0))
        t += 120
    assert det.is_ready(t)
    assert 1.4 <= det.threshold <= 1.6  # 5 × 0.3


def test_rise_and_end():
    det = _learned(floor=4)  # humidity floor dominates (5 × 0.5 = 2.5)
    t = DAY + 1000
    out = []
    for v in (55, 55, 56, 60, 66, 72, 75):
        out += det.update(t, v)
        t += 60
    assert [s.name for s in out] == ["rise"]
    for v in (74, 70, 65, 60, 57):
        out += det.update(t, v)
        t += 120
    assert [s.name for s in out] == ["rise", "rise_end"]


def test_fall():
    det = _learned(floor=1.0, noise=0.1)
    t = DAY + 1000
    out = []
    for v in (22.0, 22.0, 21.5, 20.5, 19.5):
        out += det.update(t, v)
        t += 60
    assert [s.name for s in out] == ["fall"]


def test_noise_ignored_and_sensitivity():
    out = []
    det = _learned(noise=200)  # power sensor with ±200 W normal swings
    t = DAY + 1000
    for i in range(200):
        out += det.update(t, 500 + (i % 3) * 100)
        t += 10
    assert out == []
    assert _learned(noise=200, sensitivity="high").threshold < det.threshold
    assert _learned(noise=200, sensitivity="low").threshold > det.threshold


def test_profile_roundtrip():
    det = _learned()
    clone = ChangeDetector(profile=det.profile())
    assert clone.threshold == det.threshold
    assert clone.is_ready(DAY + 1)


def test_counter_rate():
    rate = CounterRate(idle_s=300)
    assert rate.update(0, 100.0) is None
    assert abs(rate.update(60, 100.1) - 6.0) < 1e-6  # 0.1 per minute = 6 per hour
    assert rate.tick(200) is None
    assert rate.tick(400) == 0.0
    assert rate.tick(500) is None  # only once
    assert rate.update(600, 0.2) is None  # daily reset ignored


def test_counter_rate_into_detector():
    rate = CounterRate(idle_s=300)
    det = _learned(noise=0.0)
    out = []
    t = DAY + 1000
    rate.update(t, 10.0)
    det.update(t, 0.0)  # idle before (rate dropped to 0 earlier)
    for _ in range(3):  # water starts flowing
        t += 30
        out += det.update(t, rate.update(t, 10.0 + (t - DAY - 1000) / 600))
    t += 400
    out += det.update(t, rate.tick(t))
    assert [s.name for s in out] == ["rise", "rise_end"]


def test_normalize():
    assert normalize("power", 2.5, "kW") == 2500
    assert normalize("power", 1, "unknown") is None
    assert normalize("humidity", 55, "%") == 55
