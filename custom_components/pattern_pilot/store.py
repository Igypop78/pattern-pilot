"""Own event database (SQLite), independent of the HA recorder.

All methods are blocking – call them from the executor. A lock makes the
single connection safe for HA's executor threads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import sqlite3
import threading
import time

from .const import MANUAL_ACTORS, SCHEMA_VERSION

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    entity_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    area TEXT,
    kind TEXT NOT NULL,
    old TEXT,
    new TEXT,
    value REAL,
    actor TEXT NOT NULL,
    user_id TEXT,
    ref TEXT,
    override INTEGER NOT NULL DEFAULT 0,
    context_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS ix_events_entity_ts ON events (entity_id, ts);
CREATE INDEX IF NOT EXISTS ix_events_actor_ts ON events (actor, ts);
CREATE TABLE IF NOT EXISTS context (
    event_id INTEGER PRIMARY KEY REFERENCES events (id) ON DELETE CASCADE,
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
    context_id: str | None = None
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


class EventStore:
    """SQLite store for Pattern Pilot."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------------
    def open(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(_SCHEMA)
            row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema', ?), ('created', ?)",
                    (str(SCHEMA_VERSION), str(time.time())),
                )
            else:
                self._migrate(conn, int(row[0]))
            conn.commit()
            self._conn = conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection, version: int) -> None:
        if version < 2:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(context)")}
            if "sun_elevation" not in cols:
                conn.execute("ALTER TABLE context ADD COLUMN sun_elevation REAL")
        if version < SCHEMA_VERSION:
            conn.execute(
                "UPDATE meta SET value=? WHERE key='schema'", (str(SCHEMA_VERSION),)
            )

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
    def write(self, rows: list[EventRow]) -> int:
        if not rows:
            return 0
        with self._lock:
            cur = self.conn.cursor()
            for r in rows:
                cur.execute(
                    "INSERT INTO events (ts, entity_id, domain, area, kind, old, new, value,"
                    " actor, user_id, ref, override, context_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        r.ts,
                        r.entity_id,
                        r.domain,
                        r.area,
                        r.kind,
                        r.old,
                        r.new,
                        r.value,
                        r.actor,
                        r.user_id,
                        r.ref,
                        int(r.override),
                        r.context_id,
                    ),
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
            # profiles of sensors not seen for 30 days
            self.conn.execute("DELETE FROM profiles WHERE updated < ?", (now - 30 * 86400,))
            self.conn.commit()

    # -- maintenance -----------------------------------------------------------
    def purge(self, keep_days: int, now: float | None = None) -> int:
        cutoff = (now or time.time()) - keep_days * 86400
        with self._lock:
            cur = self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self.conn.execute(
                "DELETE FROM context WHERE event_id NOT IN (SELECT id FROM events)"
            )
            self.conn.commit()
            return cur.rowcount

    def vacuum(self) -> None:
        with self._lock:
            self.conn.execute("VACUUM")

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
            today = c.execute(
                "SELECT COUNT(*) FROM events WHERE ts >= ?", (day_start,)
            ).fetchone()[0]
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
        days = 0
        if first_ts is not None:
            days = int((time.time() - first_ts) // 86400)
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
                "SELECT ts, entity_id, kind, old, new, value, actor, ref, override"
                " FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
