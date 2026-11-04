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
