"""Pattern mining tests (pure Python)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.pattern_pilot.analysis import (
    Analyzer,
    EntityInfo,
    Input,
    Manual,
    Override,
    Trig,
    build_automation,
)

TZ = ZoneInfo("Europe/Bratislava")
START = datetime(2026, 11, 2, 0, 0, tzinfo=TZ)  # Monday
NOW = START + timedelta(days=15, hours=12)


def ts(day: int, hh: int, mm: int, ss: int = 0) -> float:
    return (START + timedelta(days=day, hours=hh, minutes=mm, seconds=ss)).timestamp()


def day_type(d: date) -> str:
    return "workday" if d.weekday() < 5 else "weekend"


def make(manual=(), triggers=(), automated=(), overrides=(), entities=None, exclude=()):
    return Input(
        manual=list(manual),
        triggers=list(triggers),
        automated=list(automated),
        overrides=list(overrides),
        tz=TZ,
        now=NOW,
        first_ts=ts(0, 8, 0) - 86400,
        day_type=day_type,
        entities=entities or {},
        exclude=set(exclude),
    )


def test_time_habit_workdays_dark():
    manual = []
    for day in range(15):
        d = (START + timedelta(days=day)).date()
        if d.weekday() < 5:
            manual.append(Manual(ts(day, 16, 40 + day % 3 * 5), "light.obyvacka_svetlo_hlavne", "light", "on", "workday", "night"))
        # random noise
        manual.append(Manual(ts(day, 8 + (day * 5) % 12, 10), "light.kuchyna", "light", "on", day_type(d), "day"))
    res = Analyzer(make(manual)).time_habits()
    habits = [s for s in res if s["entity_id"] == "light.obyvacka_svetlo_hlavne"]
    assert len(habits) == 1
    h = habits[0]
    assert h["days"] == "workday"
    assert h["dark"] is True
    assert "16:40" <= h["at"] <= "16:55"
    assert h["hits"] >= 8 and h["support"] >= 0.9
    assert len(h["strip"]) == 14
    assert not [s for s in res if s["entity_id"] == "light.kuchyna"]


def test_time_habit_already_automated_is_skipped():
    manual = [Manual(ts(day, 7, 0), "light.x", "light", "on", "workday", "day") for day in range(15)]
    auto = [Trig(ts(day, 7, 5), "light.x", "light", "on") for day in range(15)]
    assert Analyzer(make(manual, automated=auto)).time_habits() == []


def test_unsafe_and_excluded_not_suggested():
    manual = [Manual(ts(d, 7, 0), "cover.garaz", "cover", "open", "workday", "day") for d in range(15)]
    manual += [Manual(ts(d, 7, 0), "lock.dvere", "lock", "unlocked", "workday", "day") for d in range(15)]
    manual += [Manual(ts(d, 7, 0), "switch.brana", "switch", "on", "workday", "day") for d in range(15)]
    ents = {"cover.garaz": EntityInfo("Garáž", device_class="garage")}
    assert Analyzer(make(manual, entities=ents, exclude={"switch.brana"})).run() == []


def test_trigger_habit_motion_then_mirror():
    manual, triggers = [], []
    for day in range(15):
        # morning: motion then mirror within a minute
        triggers.append(Trig(ts(day, 6, 40), "binary_sensor.kupelna_hore_pohyb", "binary_sensor", "on"))
        triggers.append(Trig(ts(day, 6, 43), "binary_sensor.kupelna_hore_pohyb", "binary_sensor", "on"))  # same episode
        manual.append(Manual(ts(day, 6, 40, 30), "light.kupelna_hore_zrkadlo", "light", "on", "workday", "night"))
        # afternoon motion without mirror (outside the learned time range)
        triggers.append(Trig(ts(day, 15, 0), "binary_sensor.kupelna_hore_pohyb", "binary_sensor", "on"))
    res = Analyzer(make(manual, triggers)).trigger_habits()
    assert len(res) == 1
    s = res[0]
    assert s["trigger_entity"] == "binary_sensor.kupelna_hore_pohyb"
    assert s["coverage"] == 1.0 and s["precision"] == 1.0
    assert s["window"][0] <= "06:10" and s["window"][1] >= "07:10"
    # the same key is not also suggested as a time habit
    kinds = [x["kind"] for x in Analyzer(make(manual, triggers)).run() if x["entity_id"] == "light.kupelna_hore_zrkadlo"]
    assert kinds == ["trigger"]


def test_trigger_ignored_when_motion_rarely_followed():
    manual, triggers = [], []
    for day in range(15):
        for h in range(7, 22):
            triggers.append(Trig(ts(day, h, 0), "binary_sensor.chodba_pohyb", "binary_sensor", "on"))
        if day % 3 == 0:
            manual.append(Manual(ts(day, 20, 0, 20), "light.chodba", "light", "on", "workday", "night"))
    assert Analyzer(make(manual, triggers)).trigger_habits() == []


def test_improvement_from_overrides():
    ref = "automation.spalna_synchronizacia_svetiel"
    auto = [Trig(ts(d, 22, 0), "light.spalna_svetla", "light", "on") for d in range(5, 14)]
    auto += [Trig(ts(d, 22, 0), "light.spalna_lampa", "light", "on") for d in range(5, 14)]
    ov = [Override(ts(d, 22, 0, 10), "light.spalna_svetla", "off", ref) for d in range(5, 14)]
    ov += [Override(ts(d, 22, 0, 12), "light.spalna_lampa", "off", ref) for d in range(5, 8)]
    # turned off by hand 90 s later = leaving the room, not an undo
    ov += [Override(ts(d, 22, 1, 30), "light.kupelna", "off", "automation.kupelna_pohyb") for d in range(5, 14)]
    auto += [Trig(ts(d, 22, 0), "light.kupelna", "light", "on") for d in range(5, 14)]
    res = Analyzer(make(automated=auto, overrides=ov)).improvements()
    assert len(res) == 1
    assert res[0]["automation"] == ref
    assert res[0]["hits"] == 12
    assert res[0]["entity_ids"] == ["light.spalna_svetla", "light.spalna_lampa"]


def test_build_automation_time_and_trigger():
    time_s = {"kind": "time", "entity_id": "light.obyvacka_svetlo_hlavne", "action": "on", "at": "16:50",
              "days": "workday", "dark": True, "hits": 9}
    auto = build_automation(time_s, EntityInfo("Obývačka svetlo hlavné", "Obývačka"), None, "sk")
    assert auto["alias"] == "Obývačka – svetlo hlavné – zapnúť okolo 16:50"
    assert auto["triggers"] == [{"trigger": "time", "at": "16:50:00"}]
    assert {"condition": "time", "weekday": ["mon", "tue", "wed", "thu", "fri"]} in auto["conditions"]
    assert auto["actions"] == [{"action": "light.turn_on", "target": {"entity_id": "light.obyvacka_svetlo_hlavne"}}]
    trig_s = {"kind": "trigger", "entity_id": "light.zrkadlo", "action": "on", "trigger_entity": "binary_sensor.pohyb",
              "trigger_state": "on", "window": ["06:10", "07:30"], "hits": 15}
    auto = build_automation(trig_s, EntityInfo("Zrkadlo"), EntityInfo("Pohyb kúpeľňa"), "en")
    assert auto["triggers"] == [{"trigger": "state", "entity_id": "binary_sensor.pohyb", "to": "on"}]
    assert {"condition": "time", "after": "06:10:00", "before": "07:30:00"} in auto["conditions"]
    assert build_automation({"kind": "improve", "entity_id": "light.a", "action": "off"}, None, None, "sk") is None


def test_trigger_same_device_and_device_link_skipped():
    manual, triggers = [], []
    for day in range(15):
        triggers.append(Trig(ts(day, 7, 0), "binary_sensor.zaluzie_input_0", "binary_sensor", "on"))
        manual.append(Manual(ts(day, 7, 0, 20), "cover.spalna_zaluzie", "cover", "open", "workday", "day"))
        triggers.append(Trig(ts(day, 19, 0), "binary_sensor.skrina_dvere", "binary_sensor", "on"))
        manual.append(Manual(ts(day, 19, 0, 1), "light.skrina", "light", "on", "workday", "night"))
    ents = {
        "binary_sensor.zaluzie_input_0": EntityInfo("Input 0", device_id="shelly1"),
        "cover.spalna_zaluzie": EntityInfo("Žalúzie", device_id="shelly1"),
    }
    assert Analyzer(make(manual, triggers, entities=ents)).trigger_habits() == []


def test_merge_same_room_and_group():
    manual = []
    for day in range(15):
        for eid in ("light.zahrada_lampas_1", "light.zahrada_lampas_2"):
            manual.append(Manual(ts(day, 16, 30), eid, "light", "on", "workday", "night"))
        manual.append(Manual(ts(day, 6, 45), "light.martin_globus", "light", "on", "workday", "night"))
        manual.append(Manual(ts(day, 6, 48), "switch.martin_ziarovka", "switch", "on", "workday", "night"))
    ents = {
        "light.zahrada_lampas_1": EntityInfo("Záhrada lampáš 1", "Záhrada"),
        "light.zahrada_lampas_2": EntityInfo("Záhrada lampáš 2", "Záhrada"),
        "light.martin_globus": EntityInfo("Martin glóbus", "Martin"),
        "switch.martin_ziarovka": EntityInfo("Martin žiarovka", "Martin"),
    }
    groups = {"light.zahrada_lampase": {"light.zahrada_lampas_1", "light.zahrada_lampas_2"}}
    inp = make(manual, entities=ents)
    inp.groups = groups
    res = Analyzer(inp).run()
    assert len(res) == 2
    by = {tuple(s["entity_ids"]): s for s in res}
    assert ("light.zahrada_lampase",) in by
    martin = by[("light.martin_globus", "switch.martin_ziarovka")]
    auto = build_automation(martin, ents, None, "sk")
    assert auto["alias"].startswith("Martin – glóbus a žiarovka – zapnúť okolo")
    assert {"action": "light.turn_on", "target": {"entity_id": "light.martin_globus"}} in auto["actions"]
    assert {"action": "switch.turn_on", "target": {"entity_id": "switch.martin_ziarovka"}} in auto["actions"]


def test_changes_right_after_time_or_sun_automation_are_not_habits():
    manual = [Manual(ts(d, 16, 20, 5), "light.spolocne_dvor_svetlo", "light", "on", "workday", "night") for d in range(15)]
    runs = [(ts(d, 16, 20), "automation.dvor_svetlo_pri_zapade", "sun") for d in range(15)]
    inp = make(manual)
    inp.runs = runs
    assert Analyzer(inp).run() == []
    # a motion-triggered automation right before a real manual action does not hide it
    manual = [Manual(ts(d, 16, 20, 5), "light.spolocne_dvor_svetlo", "light", "on", "workday", "night") for d in range(15)]
    inp = make(manual)
    inp.runs = [(ts(d, 16, 20), "automation.upozornenie", "state of binary_sensor.pohyb") for d in range(15)]
    assert len(Analyzer(inp).run()) == 1
