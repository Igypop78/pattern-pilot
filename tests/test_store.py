"""Event store tests (pure Python + sqlite)."""

import time

from custom_components.pattern_pilot.store import EventRow, EventStore


def _row(ts, actor="human", context=None):
    return EventRow(
        ts=ts,
        entity_id="light.kupelna_dole",
        domain="light",
        area="bathroom",
        kind="state",
        old="off",
        new="on",
        value=255,
        actor=actor,
        context=context,
    )


def test_write_stats_purge(tmp_path):
    store = EventStore(str(tmp_path / "pp.db"))
    store.open()
    now = time.time()
    rows = [
        _row(now - 200 * 86400),
        _row(now - 10, context={"day_type": "workday", "sun": "night", "people_home": 2}),
        _row(now - 5, actor="automation"),
        _row(now - 1, actor="physical"),
    ]
    assert store.write(rows) == 4
    stats = store.stats(day_start=now - 3600)
    assert stats.total == 4
    assert stats.manual_total == 3
    assert stats.today == 3
    assert stats.manual_today == 2
    assert stats.by_actor["automation"] == 1
    assert stats.days >= 199
    ctx = store.conn.execute("SELECT day_type, people_home FROM context").fetchall()
    assert ctx == [("workday", 2)]

    removed = store.purge(keep_days=120, now=now)
    assert removed == 1
    assert store.stats(day_start=now - 3600).total == 3
    store.vacuum()
    assert len(store.recent(10)) == 3
    store.close()


def test_reopen_keeps_data(tmp_path):
    path = str(tmp_path / "pp.db")
    store = EventStore(path)
    store.open()
    store.write([_row(time.time())])
    store.close()
    store2 = EventStore(path)
    store2.open()
    assert store2.stats(0).total == 1
    store2.close()


def test_profiles(tmp_path):
    store = EventStore(str(tmp_path / "pp.db"))
    store.open()
    store.save_profiles({"sensor.a": {"first_ts": 1.0, "ranges": [0.5, 0.6]}})
    store.save_profiles({"sensor.a": {"first_ts": 1.0, "ranges": [0.7]}, "sensor.b": {"x": 1}})
    profiles = store.load_profiles()
    assert profiles["sensor.a"]["ranges"] == [0.7]
    assert "sensor.b" in profiles
    store.close()


def test_migrate_schema_1(tmp_path):
    import sqlite3

    path = str(tmp_path / "pp.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('schema', '1');
        CREATE TABLE context (event_id INTEGER PRIMARY KEY, day_type TEXT, sun TEXT,
            lux REAL, temperature REAL, people_home INTEGER);
        """
    )
    conn.commit()
    conn.close()
    store = EventStore(path)
    store.open()
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(context)")}
    assert "sun_elevation" in cols
    assert store.conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] == "3"
    store.write([_row(time.time(), context={"day_type": "holiday", "sun_elevation": 12.5})])
    assert store.conn.execute("SELECT sun_elevation FROM context").fetchone()[0] == 12.5
    store.close()


def test_migrate_to_3_reclassifies_device_programs(tmp_path):
    import sqlite3

    path = str(tmp_path / "pp.db")
    store = EventStore(path)
    store.open()
    rows = [_row(time.time()), _row(time.time())]
    rows[1].entity_id, rows[1].domain, rows[1].actor = "climate.trv", "climate", "physical"
    rows[1].context = {"day_type": "workday"}
    rows[0].actor = "physical"
    store.write(rows)
    store.conn.execute("UPDATE meta SET value='2' WHERE key='schema'")
    store.conn.commit()
    store.close()
    store = EventStore(path)
    store.open()
    actors = dict(store.conn.execute("SELECT domain, actor FROM events"))
    assert actors == {"light": "physical", "climate": "device"}
    assert store.conn.execute("SELECT COUNT(*) FROM context").fetchone()[0] == 0
    store.close()
