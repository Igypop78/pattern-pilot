"""Pattern mining – turns recorded events into automation suggestions.

Pure Python (no Home Assistant imports) so it can be tested alone.

Kinds:
* ``time``     – the same manual action at a similar time of day (+ day type, darkness)
* ``trigger``  – after A (motion, door, person, button) you do B by hand within 90 s
* ``improve``  – an automation you keep reverting by hand (override)

Every candidate is backtested on the recorded days: how often it would have
been right and how often it would have fired for nothing.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo
import hashlib
from statistics import median
from typing import Any, Callable

# --- tuning ---------------------------------------------------------------------
MIN_HITS = 5  # days / occurrences supporting a pattern
MIN_SUPPORT = 0.6  # time habit: share of eligible days
MAX_FALSE_PER_WEEK = 2.0  # time habit: fires for nothing at most this often
WINDOW_MIN = 40  # time habit: width of the time window (minutes)
TRIGGER_DELAY_S = 90  # trigger: B within this after A
TRIGGER_EPISODE_S = 600  # trigger: A again within 10 min = same episode
MIN_COVERAGE = 0.5  # trigger: share of B explained by A
MIN_PRECISION = 0.4  # trigger: share of A (in the time range) followed by B
MIN_OVERRIDES = 3  # improve: reverts in the last 14 days
STRIP_DAYS = 14

# what may be suggested and how (state → service)
_ON_OFF = {"on": "turn_on", "off": "turn_off"}
SERVICES: dict[str, dict[str, str]] = {
    "light": _ON_OFF,
    "switch": _ON_OFF,
    "fan": _ON_OFF,
    "input_boolean": _ON_OFF,
    "media_player": _ON_OFF,
    "humidifier": _ON_OFF,
    "cover": {"open": "open_cover", "closed": "close_cover"},
    "scene": {"activated": "turn_on"},
    "script": {"on": "turn_on"},
}
# never open these automatically (security)
UNSAFE_COVER_CLASSES = ("garage", "gate", "door")
TRIGGER_STATES: dict[str, tuple[str, ...]] = {
    "binary_sensor": ("on",),
    "person": ("home", "not_home"),
}


@dataclass(slots=True)
class Manual:
    ts: float
    entity_id: str
    domain: str
    new: str
    day_type: str | None = None
    sun: str | None = None


@dataclass(slots=True)
class Trig:
    ts: float
    entity_id: str
    domain: str
    new: str


@dataclass(slots=True)
class Override:
    ts: float
    entity_id: str
    new: str
    ref: str


@dataclass
class EntityInfo:
    name: str
    area: str | None = None
    device_class: str | None = None


@dataclass
class Input:
    manual: list[Manual]
    triggers: list[Trig]
    automated: list[Trig]  # changes made by automations (already automated?)
    overrides: list[Override]
    tz: tzinfo
    now: datetime
    first_ts: float
    day_type: Callable[[date], str]
    entities: dict[str, EntityInfo] = field(default_factory=dict)
    exclude: set[str] = field(default_factory=set)


def _sid(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _group(day_type: str) -> str:
    return "workday" if day_type == "workday" else "weekend"


def _hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def suggestible(domain: str, new: str, info: EntityInfo | None) -> bool:
    service = SERVICES.get(domain, {}).get(new)
    if service is None:
        return False
    if domain == "cover" and new == "open" and info and info.device_class in UNSAFE_COVER_CLASSES:
        return False
    return True


class Analyzer:
    """Runs all miners on one ``Input``."""

    def __init__(self, data: Input) -> None:
        self.d = data
        today = data.now.astimezone(data.tz).date()
        first = datetime.fromtimestamp(data.first_ts, data.tz).date()
        # full days only: from the first full day to yesterday
        start = first + timedelta(days=1)
        self.days: list[date] = [
            start + timedelta(days=i) for i in range((today - start).days)
        ]
        self.dayset = set(self.days)
        self.day_types = {d: data.day_type(d) for d in self.days}

    def local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts, self.d.tz)

    # ------------------------------------------------------------------------------
    def run(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        trig = self.trigger_habits()
        trig_keys = {(s["entity_id"], s["action"]) for s in trig}
        out += trig
        out += [s for s in self.time_habits() if (s["entity_id"], s["action"]) not in trig_keys]
        out += self.improvements()
        out.sort(key=lambda s: s["score"], reverse=True)
        return out

    def _strip(self, hit_days: set[date], eligible: set[date]) -> list[int]:
        """Last 14 days: 2 = pattern happened, 1 = eligible day without it, 0 = not eligible."""
        days = self.days[-STRIP_DAYS:]
        return [2 if d in hit_days else 1 if d in eligible else 0 for d in days]

    # -- time habits -----------------------------------------------------------------
    def time_habits(self) -> list[dict[str, Any]]:
        d = self.d
        groups: dict[tuple[str, str], list[tuple[date, int, str | None]]] = defaultdict(list)
        for m in d.manual:
            if m.entity_id in d.exclude or not suggestible(m.domain, m.new, d.entities.get(m.entity_id)):
                continue
            lt = self.local(m.ts)
            if lt.date() in self.dayset:
                groups[(m.entity_id, m.new)].append((lt.date(), lt.hour * 60 + lt.minute, m.sun))

        automated: dict[tuple[str, str], list[tuple[date, int]]] = defaultdict(list)
        for a in d.automated:
            lt = self.local(a.ts)
            automated[(a.entity_id, a.new)].append((lt.date(), lt.hour * 60 + lt.minute))

        out = []
        for (entity_id, action), occ in groups.items():
            if len({o[0] for o in occ}) < MIN_HITS:
                continue
            best = None
            for dg in ("all", "workday", "weekend"):
                eligible = {x for x in self.days if dg == "all" or _group(self.day_types[x]) == dg}
                if len(eligible) < MIN_HITS:
                    continue
                cand = self._best_window([o for o in occ if o[0] in eligible])
                if cand is None:
                    continue
                start, hits = cand
                support = len(hits) / len(eligible)
                false_per_week = (len(eligible) - len(hits)) / max(1, len(self.days)) * 7
                if len(hits) < MIN_HITS or support < MIN_SUPPORT or false_per_week > MAX_FALSE_PER_WEEK:
                    continue
                # "all" wins unless a day type is clearly better
                score = support - (0.05 if dg != "all" else 0)
                if best is None or score > best[0]:
                    best = (score, dg, start, hits, eligible, support, false_per_week)
            if best is None:
                continue
            _score, dg, start, hits, eligible, support, false_per_week = best
            times = sorted(hits.values())
            at = int(round(median(times) / 5) * 5)
            window_end = start + WINDOW_MIN
            # already done by an automation in that window on most days?
            done = {
                day
                for day, minute in automated.get((entity_id, action), [])
                if day in eligible and start - 15 <= minute <= window_end + 15
            }
            if len(done) >= 0.5 * len(eligible):
                continue
            hit_sun = [s for (day, minute, s) in occ if day in hits and hits[day] == minute]
            dark = bool(hit_sun) and sum(1 for s in hit_sun if s == "night") >= 0.9 * len(hit_sun)
            out.append(
                {
                    "id": _sid("time", entity_id, action, dg),
                    "kind": "time",
                    "entity_id": entity_id,
                    "action": action,
                    "at": _hhmm(at),
                    "window": [_hhmm(start), _hhmm(window_end)],
                    "days": dg,
                    "dark": dark,
                    "hits": len(hits),
                    "eligible": len(eligible),
                    "support": round(support, 2),
                    "false_per_week": round(false_per_week, 1),
                    "strip": self._strip(set(hits), eligible),
                    "score": round(support * min(1, len(hits) / 10), 3),
                }
            )
        return out

    @staticmethod
    def _best_window(occ: list[tuple[date, int, Any]]) -> tuple[int, dict[date, int]] | None:
        """Window of WINDOW_MIN minutes covering the most days. Returns (start, {day: minute})."""
        if not occ:
            return None
        pts = sorted((minute, day) for day, minute, _ in occ)
        best_start, best_hits = 0, {}
        j = 0
        for i, (start, _) in enumerate(pts):
            while j < len(pts) and pts[j][0] <= start + WINDOW_MIN:
                j += 1
            hits: dict[date, int] = {}
            for minute, day in pts[i:j]:
                hits.setdefault(day, minute)
            if len(hits) > len(best_hits):
                best_start, best_hits = start, hits
        return best_start, best_hits

    # -- trigger → action -----------------------------------------------------------------
    def trigger_habits(self) -> list[dict[str, Any]]:
        d = self.d
        by_trigger: dict[tuple[str, str], list[float]] = defaultdict(list)
        for t in sorted(d.triggers, key=lambda x: x.ts):
            if t.entity_id in d.exclude:
                continue
            if t.domain == "event" or t.new in TRIGGER_STATES.get(t.domain, ()):
                key = (t.entity_id, "event" if t.domain == "event" else t.new)
                by_trigger[key].append(t.ts)
        # episodes: a trigger repeating within 10 min is the same activity
        episodes: dict[tuple[str, str], list[float]] = {}
        for key, ts_list in by_trigger.items():
            ep: list[float] = []
            last = None
            for ts in ts_list:
                if last is None or ts - last > TRIGGER_EPISODE_S:
                    ep.append(ts)
                last = ts
            episodes[key] = ep

        manual: dict[tuple[str, str], list[float]] = defaultdict(list)
        for m in d.manual:
            if m.entity_id in d.exclude or not suggestible(m.domain, m.new, d.entities.get(m.entity_id)):
                continue
            manual[(m.entity_id, m.new)].append(m.ts)

        out = []
        for (entity_id, action), b_list in manual.items():
            if len(b_list) < MIN_HITS:
                continue
            b_list.sort()
            best = None
            for (t_entity, t_state), a_all in by_trigger.items():
                if t_entity == entity_id:
                    continue
                co = []
                for b in b_list:
                    i = bisect_right(a_all, b)
                    if i and b - a_all[i - 1] <= TRIGGER_DELAY_S:
                        co.append(b)
                if len(co) < MIN_HITS:
                    continue
                coverage = len(co) / len(b_list)
                if coverage < MIN_COVERAGE:
                    continue
                minutes = sorted(self.local(b).hour * 60 + self.local(b).minute for b in co)
                lo, hi = max(0, minutes[0] - 30), min(1439, minutes[-1] + 30)
                all_day = hi - lo >= 20 * 60
                eps = [
                    a
                    for a in episodes[(t_entity, t_state)]
                    if all_day or lo <= self.local(a).hour * 60 + self.local(a).minute <= hi
                ]
                if not eps:
                    continue
                followed = 0
                for a in eps:
                    k = bisect_left(b_list, a)
                    if k < len(b_list) and b_list[k] - a <= TRIGGER_DELAY_S + TRIGGER_EPISODE_S:
                        followed += 1
                precision = followed / len(eps)
                if precision < MIN_PRECISION:
                    continue
                score = coverage * precision * min(1, len(co) / 10)
                if best is None or score > best[0]:
                    best = (score, t_entity, t_state, co, coverage, precision, lo, hi, all_day, eps)
            if best is None:
                continue
            score, t_entity, t_state, co, coverage, precision, lo, hi, all_day, eps = best
            hit_days = {self.local(b).date() for b in co}
            ep_days = {self.local(a).date() for a in eps}
            out.append(
                {
                    "id": _sid("trigger", entity_id, action, t_entity, t_state),
                    "kind": "trigger",
                    "entity_id": entity_id,
                    "action": action,
                    "trigger_entity": t_entity,
                    "trigger_state": t_state,
                    "window": None if all_day else [_hhmm(lo), _hhmm(hi)],
                    "hits": len(co),
                    "total": len(b_list),
                    "coverage": round(coverage, 2),
                    "precision": round(precision, 2),
                    "strip": self._strip(hit_days & self.dayset, ep_days & self.dayset),
                    "score": round(score, 3),
                }
            )
        return out

    # -- improve existing automations ------------------------------------------------------
    def improvements(self) -> list[dict[str, Any]]:
        d = self.d
        since = (d.now - timedelta(days=STRIP_DAYS)).timestamp()
        groups: dict[tuple[str, str], list[Override]] = defaultdict(list)
        for o in d.overrides:
            if o.ts >= since and o.ref and o.ref not in d.exclude:
                groups[(o.ref, o.entity_id)].append(o)
        out = []
        for (ref, entity_id), items in groups.items():
            if len(items) < MIN_OVERRIDES:
                continue
            days = {self.local(o.ts).date() for o in items}
            states = defaultdict(int)
            for o in items:
                states[o.new] += 1
            out.append(
                {
                    "id": _sid("improve", ref, entity_id),
                    "kind": "improve",
                    "automation": ref,
                    "entity_id": entity_id,
                    "action": max(states, key=states.get),
                    "hits": len(items),
                    "days_count": len(days),
                    "strip": self._strip(days, self.dayset),
                    "score": round(min(1, len(items) / 10), 3),
                }
            )
        return out


# --- automation config ---------------------------------------------------------------

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
_WEEKEND = ["sat", "sun"]


def _what(domain: str, action: str, lang: str) -> str:
    sk = lang == "sk"
    words = {
        ("on",): ("zapnúť", "turn on"),
        ("off",): ("vypnúť", "turn off"),
        ("open",): ("otvoriť", "open"),
        ("closed",): ("zatvoriť", "close"),
        ("activated",): ("aktivovať", "activate"),
    }
    for keys, (s, e) in words.items():
        if action in keys:
            return s if sk else e
    return action


def build_automation(s: dict[str, Any], info: EntityInfo | None, trig_info: EntityInfo | None, lang: str) -> dict[str, Any] | None:
    """Home Assistant automation config for a suggestion (or None for 'improve')."""
    if s["kind"] not in ("time", "trigger"):
        return None
    entity_id, action = s["entity_id"], s["action"]
    domain = entity_id.split(".")[0]
    service = SERVICES.get(domain, {}).get(action)
    if service is None:
        return None
    sk = lang == "sk"
    name = info.name if info else entity_id
    area = info.area if info and info.area else None
    what = _what(domain, action, lang)

    conditions: list[dict[str, Any]] = []
    if s["kind"] == "time":
        triggers = [{"trigger": "time", "at": f"{s['at']}:00"}]
        if s["days"] == "workday":
            conditions.append({"condition": "time", "weekday": _WEEKDAYS})
        elif s["days"] == "weekend":
            conditions.append({"condition": "time", "weekday": _WEEKEND})
        if s.get("dark"):
            conditions.append({"condition": "state", "entity_id": "sun.sun", "state": "below_horizon"})
        desc_core = (
            f"okolo {s['at']}" if sk else f"around {s['at']}"
        )
    else:
        t_entity, t_state = s["trigger_entity"], s["trigger_state"]
        if t_entity.startswith("event."):
            triggers = [{"trigger": "state", "entity_id": t_entity, "not_from": ["unavailable", "unknown"]}]
        else:
            triggers = [{"trigger": "state", "entity_id": t_entity, "to": t_state}]
        if s.get("window"):
            conditions.append(
                {"condition": "time", "after": f"{s['window'][0]}:00", "before": f"{s['window'][1]}:00"}
            )
        t_name = trig_info.name if trig_info else t_entity
        desc_core = f"pri {t_name}" if sk else f"on {t_name}"
    # do nothing if it is already in the target state
    if domain in ("light", "switch", "fan", "input_boolean", "media_player", "humidifier", "cover"):
        conditions.append(
            {"condition": "not", "conditions": [{"condition": "state", "entity_id": entity_id, "state": action}]}
        )

    prefix = f"{area} – " if area else ""
    short = name[len(area) + 1 :] if area and name.lower().startswith(area.lower() + " ") else name
    alias = f"{prefix}{short} – {what} {desc_core}"
    evidence = (
        f"Návrh Pattern Pilot: {s['hits']}× zistené" if sk else f"Pattern Pilot suggestion: seen {s['hits']}×"
    )
    return {
        "alias": alias[:120],
        "description": evidence,
        "mode": "single",
        "triggers": triggers,
        "conditions": conditions,
        "actions": [{"action": f"{domain}.{service}", "target": {"entity_id": entity_id}}],
    }
