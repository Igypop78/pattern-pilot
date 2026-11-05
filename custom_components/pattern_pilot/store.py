"""Own event database (SQLite), independent of the HA recorder.

All methods are blocking – call them from the executor. A lock makes the
single connection safe for HA's executor threads.

Schema 4 (compact): entity ids are stored once in ``entities`` and events
refer to them by number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import sqlite3
import threading
import time

from .const import ACTION_DOMAINS, MANUAL_ACTORS, PHYSICAL_MANUAL_DOMAINS, SCHEMA_VERSION

_TABLES = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    entity_id TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    area TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    entity INTEGER NOT NULL,
    kind TEXT NOT NULL,
    old TEXT,
    new TEXT,
    value REAL,
    actor TEXT NOT NULL,
    user_id TEXT,
    ref TEXT,
    override INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ev_ts ON events (ts);
CREATE INDEX IF NOT EXISTS ix_ev_entity_ts ON events (entity, ts);
CREATE TABLE IF NOT EXISTS context (
    event_id INTEGER PRIMARY KEY,
    day_type TEXT,
    sun TEXT,
    lux REAL,
    temperature REAL,
    people_home INTEGER,
    sun_elevation REAL
);
CREATE TABLE IF NOT EXISTS profiles (
    entity_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated REAL NOT NULL
);
"""

_EVENT_COLS = "ev.ts, en.entity_id, en.domain, ev.kind, ev.old, ev.new, ev.value, ev.actor, ev.ref, ev.override"


@dataclass(slots=True)
class EventRow:
    """One row to be written."""

    ts: float
    entity_id: str
    domain: str
    area: str | None
    kind: str
    old: str | None
    new: str | None
    value: float | None
    actor: str
    user_id: str | None = None
    ref: str | None = None
    override: bool = False
    context_id: str | None = None  # not stored (kept for callers)
    context: dict | None = field(default=None)


@dataclass(slots=True)
class StoreStats:
    """Summary for sensors and diagnostics."""

    total: int = 0
    manual_total: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    days: int = 0
    today: int = 0
    manual_today: int = 0
    size_bytes: int = 0
    by_actor: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


class EventStore:
    """SQLite store for Pattern Pilot."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._ids: dict[str, tuple[int, str | None]] = {}

    # -- lifecycle -------------------------------------------------------------
    def open(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row is None:
                conn.executescript(_TABLES)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema', ?), ('created', ?)",
                    (str(SCHEMA_VERSION), str(time.time())),
                )
            elif int(row[0]) < SCHEMA_VERSION:
                self._migrate(conn, int(row[0]))
            conn.commit()
            self._conn = conn
            self._ids = {
                eid: (num, area)
                for num, eid, area in conn.execute("SELECT id, entity_id, area FROM entities")
            }

    @staticmethod
    def _migrate(conn: sqlite3.Connection, version: int) -> None:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        legacy = "events" in tables and "entity_id" in _columns(conn, "events")
        if "context" in tables and "sun_elevation" not in _columns(conn, "context"):
            conn.execute("ALTER TABLE context ADD COLUMN sun_elevation REAL")
        if legacy and version < 3:
            # changes outside HA on thermostats, vacuums … are the device's own program
            marks = ",".join("?" * len(PHYSICAL_MANUAL_DOMAINS))
            conn.execute(
                f"UPDATE events SET actor='device' WHERE actor='physical' AND domain NOT IN ({marks})",
                PHYSICAL_MANUAL_DOMAINS,
            )
            if "context" in tables:
                conn.execute(
                    "DELETE FROM context WHERE event_id IN (SELECT id FROM events WHERE actor='device')"
                )
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")
        if legacy:
            # schema 4: entity ids stored once, no context_id, fewer indexes
            for ix in ("ix_events_ts", "ix_events_entity_ts", "ix_events_actor_ts"):
                conn.execute(f"DROP INDEX IF EXISTS {ix}")
            conn.execute("ALTER TABLE events RENAME TO events_old")
        if "context" in tables:
            conn.execute("ALTER TABLE context RENAME TO context_old")
        conn.executescript(_TABLES)
        if legacy:
            conn.execute(
                "INSERT INTO entities (entity_id, domain, area)"
                " SELECT entity_id, MAX(domain), MAX(area) FROM events_old GROUP BY entity_id"
            )
            conn.execute(
                "INSERT INTO events (id, ts, entity, kind, old, new, value, actor, user_id, ref, override)"
                " SELECT o.id, o.ts, e.id, o.kind, o.old, o.new, o.value, o.actor, o.user_id, o.ref, o.override"
                " FROM events_old o JOIN entities e ON e.entity_id = o.entity_id"
            )
            conn.execute("DROP TABLE events_old")
        if "context" in tables:
            conn.execute(
                "INSERT INTO context (event_id, day_type, sun, lux, temperature, people_home, sun_elevation)"
                " SELECT event_id, day_type, sun, lux, temperature, people_home, sun_elevation FROM context_old"
                " WHERE event_id IN (SELECT id FROM events)"
            )
            conn.execute("DROP TABLE context_old")
        conn.execute("UPDATE meta SET value=? WHERE key='schema'", (str(SCHEMA_VERSION),))
        conn.commit()
        conn.execute("VACUUM")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("store not open")
        return self._conn

    # -- writing ---------------------------------------------------------------
    def _entity(self, cur: sqlite3.Cursor, entity_id: str, domain: str, area: str | None) -> int:
        known = self._ids.get(entity_id)
        if known is not None:
            num, old_area = known
            if area and area != old_area:
                cur.execute("UPDATE entities SET area=? WHERE id=?", (area, num))
                self._ids[entity_id] = (num, area)
            return num
        cur.execute(
            "INSERT OR IGNORE INTO entities (entity_id, domain, area) VALUES (?,?,?)",
            (entity_id, domain, area),
        )
        num = cur.execute("SELECT id FROM entities WHERE entity_id=?", (entity_id,)).fetchone()[0]
        self._ids[entity_id] = (num, area)
        return num

    def write(self, rows: list[EventRow]) -> int:
        if not rows:
            return 0
        with self._lock:
            cur = self.conn.cursor()
            for r in rows:
                num = self._entity(cur, r.entity_id, r.domain, r.area)
                cur.execute(
                    "INSERT INTO events (ts, entity, kind, old, new, value, actor, user_id, ref, override)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (r.ts, num, r.kind, r.old, r.new, r.value, r.actor, r.user_id, r.ref, int(r.override)),
                )
                if r.context:
                    c = r.context
                    cur.execute(
                        "INSERT INTO context (event_id, day_type, sun, lux, temperature,"
                        " people_home, sun_elevation) VALUES (?,?,?,?,?,?,?)",
                        (
                            cur.lastrowid,
                            c.get("day_type"),
                            c.get("sun"),
                            c.get("lux"),
                            c.get("temperature"),
                            c.get("people_home"),
                            c.get("sun_elevation"),
                        ),
                    )
            self.conn.commit()
        return len(rows)

    # -- detector profiles (learned normal variation) ------------------------------
    def load_profiles(self) -> dict[str, dict]:
        with self._lock:
            rows = self.conn.execute("SELECT entity_id, data FROM profiles").fetchall()
        out: dict[str, dict] = {}
        for entity_id, data in rows:
            try:
                out[entity_id] = json.loads(data)
            except ValueError:
                continue
        return out

    def save_profiles(self, profiles: dict[str, dict]) -> None:
        if not profiles:
            return
        now = time.time()
        with self._lock:
            self.conn.executemany(
                "INSERT INTO profiles (entity_id, data, updated) VALUES (?,?,?)"
                " ON CONFLICT(entity_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                [(eid, json.dumps(p), now) for eid, p in profiles.items()],
            )
            self.conn.execute("DELETE FROM profiles WHERE updated < ?", (now - 30 * 86400,))
            self.conn.commit()

    # -- maintenance -----------------------------------------------------------
    def purge(self, keep_days: int, now: float | None = None) -> int:
        cutoff = (now or time.time()) - keep_days * 86400
        with self._lock:
            cur = self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self.conn.execute("DELETE FROM context WHERE event_id NOT IN (SELECT id FROM events)")
            self.conn.commit()
            return cur.rowcount

    def vacuum(self) -> None:
        with self._lock:
            self.conn.execute("VACUUM")
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # -- reading ---------------------------------------------------------------
    def stats(self, day_start: float) -> StoreStats:
        """Counts; ``day_start`` = epoch of local midnight today."""
        manual = tuple(MANUAL_ACTORS)
        marks = ",".join("?" * len(manual))
        with self._lock:
            c = self.conn
            total, first_ts, last_ts = c.execute(
                "SELECT COUNT(*), MIN(ts), MAX(ts) FROM events"
            ).fetchone()
            manual_total = c.execute(
                f"SELECT COUNT(*) FROM events WHERE actor IN ({marks})", manual
            ).fetchone()[0]
            today = c.execute("SELECT COUNT(*) FROM events WHERE ts >= ?", (day_start,)).fetchone()[0]
            manual_today = c.execute(
                f"SELECT COUNT(*) FROM events WHERE ts >= ? AND actor IN ({marks})",
                (day_start, *manual),
            ).fetchone()[0]
            by_actor = dict(c.execute("SELECT actor, COUNT(*) FROM events GROUP BY actor"))
            by_kind = dict(c.execute("SELECT kind, COUNT(*) FROM events GROUP BY kind"))
        size = 0
        for suffix in ("", "-wal"):
            try:
                size += os.path.getsize(self.path + suffix)
            except OSError:
                pass
        days = int((time.time() - first_ts) // 86400) if first_ts is not None else 0
        return StoreStats(
            total=total,
            manual_total=manual_total,
            first_ts=first_ts,
            last_ts=last_ts,
            days=days,
            today=today,
            manual_today=manual_today,
            size_bytes=size,
            by_actor=by_actor,
            by_kind=by_kind,
        )

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(
                f"SELECT {_EVENT_COLS} FROM events ev JOIN entities en ON en.id = ev.entity"
                " ORDER BY ev.id DESC LIMIT ?",
                (limit,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def top_entities(self, since: float, limit: int = 20) -> list[dict]:
        """Entities producing the most events (diagnostics)."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT en.entity_id, COUNT(*), SUM(ev.kind='signal'), SUM(ev.kind='run')"
                " FROM events ev JOIN entities en ON en.id = ev.entity WHERE ev.ts >= ?"
                " GROUP BY ev.entity ORDER BY 2 DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        return [
            {"entity_id": r[0], "events": r[1], "signals": r[2], "runs": r[3]} for r in rows
        ]

    def overview(self, since_hourly: float, since_week: float, recent_limit: int = 12) -> dict:
        """Data for the card: manual action times, who controls the house, top entities, recent events."""
        manual = tuple(MANUAL_ACTORS)
        m_marks = ",".join("?" * len(manual))
        domains = tuple(ACTION_DOMAINS)
        d_marks = ",".join("?" * len(domains))
        with self._lock:
            c = self.conn
            manual_ts = [
                r[0]
                for r in c.execute(
                    f"SELECT ts FROM events WHERE ts >= ? AND actor IN ({m_marks})",
                    (since_hourly, *manual),
                )
            ]
            actors = dict(
                c.execute(
                    "SELECT ev.actor, COUNT(*) FROM events ev JOIN entities en ON en.id = ev.entity"
                    f" WHERE ev.ts >= ? AND ev.kind IN ('state','attr') AND en.domain IN ({d_marks})"
                    " GROUP BY ev.actor",
                    (since_week, *domains),
                )
            )
            top = [
                {"entity_id": r[0], "count": r[1], "last": r[2]}
                for r in c.execute(
                    "SELECT en.entity_id, COUNT(*), MAX(ev.ts) FROM events ev"
                    " JOIN entities en ON en.id = ev.entity"
                    f" WHERE ev.ts >= ? AND ev.actor IN ({m_marks})"
                    " GROUP BY ev.entity ORDER BY 2 DESC LIMIT 6",
                    (since_week, *manual),
                )
            ]
            signals_week = c.execute(
                "SELECT COUNT(*) FROM events WHERE ts >= ? AND kind='signal' AND new IN ('rise','fall')",
                (since_week,),
            ).fetchone()[0]
            cur = c.execute(
                f"SELECT {_EVENT_COLS} FROM events ev JOIN entities en ON en.id = ev.entity"
                " WHERE NOT (ev.kind='signal' AND ev.new IN ('rise_end','fall_end'))"
                " ORDER BY ev.id DESC LIMIT ?",
                (recent_limit,),
            )
            cols = [d[0] for d in cur.description]
            recent = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        return {
            "manual_ts": manual_ts,
            "actors": actors,
            "top": top,
            "signals_week": signals_week,
            "recent": recent,
        }
