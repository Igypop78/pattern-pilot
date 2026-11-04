"""Detector tests (pure Python)."""

from custom_components.pattern_pilot.detectors import (
    HumidityRiseDetector,
    PowerStepDetector,
    WaterUseDetector,
    to_litres,
    to_watts,
)


def test_shower_detected_and_ended():
    det = HumidityRiseDetector(rise=8)
    t = 0.0
    out = []
    for v in (55, 55, 56, 60, 66, 72, 75):  # fast rise
        out += det.update(t, v)
        t += 60
    assert [s.name for s in out] == ["shower_start"]
    assert out[0].value >= 8
    for v in (74, 70, 65, 60, 58):
        out += det.update(t, v)
        t += 120
    assert [s.name for s in out] == ["shower_start", "shower_end"]


def test_slow_humidity_drift_is_not_shower():
    det = HumidityRiseDetector(rise=8, window_s=600)
    out = []
    for i in range(60):  # +0.5 % every 2 min = 15 % in 2 h
        out += det.update(i * 120.0, 50 + i * 0.5)
    assert out == []


def test_power_step():
    det = PowerStepDetector(step=1500)
    out = []
    t = 0.0
    for v in (300, 320, 310, 2300, 2350, 2290, 400, 350):
        out += det.update(t, v)
        t += 30
    names = [s.name for s in out]
    assert names == ["load_start", "load_end"]
    assert out[0].value == 2000


def test_power_noise_ignored():
    det = PowerStepDetector(step=1500)
    out = []
    for i in range(100):
        out += det.update(i * 10.0, 400 + (i % 5) * 100)
    assert out == []


def test_water_total_meter():
    det = WaterUseDetector(min_litres=3, gap_s=180)
    out = []
    total = 1000.0
    out += det.update(0, total)
    for t in (60, 90, 120):
        total += 2.0
        out += det.update(t, total)
    assert out == []
    out += det.tick(200)
    assert out == []
    out += det.tick(400)
    assert len(out) == 1
    assert out[0].name == "water_use"
    assert out[0].ts == 60
    assert out[0].value == 6.0


def test_water_small_use_dropped():
    det = WaterUseDetector(min_litres=3, gap_s=180)
    det.update(0, 10.0)
    det.update(30, 11.0)
    assert det.tick(1000) == []


def test_water_flow():
    det = WaterUseDetector(min_litres=3, gap_s=60, flow=True)
    out = []
    out += det.update(0, 6.0)  # 6 l/min
    out += det.update(60, 6.0)
    out += det.update(120, 0.0)
    out += det.tick(500)
    assert len(out) == 1
    assert out[0].value == 12.0


def test_units():
    assert to_watts(2.5, "kW") == 2500
    assert to_litres(1.5, "m³") == 1500
    assert to_watts(1, "unknown") is None
