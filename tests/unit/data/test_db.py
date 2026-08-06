"""Tests for the database connection factory."""

import sqlite3
import threading
import time

import pytest

from data.db import apply_schema, connect, transaction


def test_connect_enables_foreign_keys():
    conn = connect(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_returns_row_objects():
    conn = connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO plants (name, location_kind, created_at) VALUES (?, ?, ?)",
        ("Basil", "indoor", "2026-01-01T00:00:00+00:00"),
    )
    row = conn.execute("SELECT name FROM plants").fetchone()
    assert row["name"] == "Basil"


def test_apply_schema_creates_every_table():
    conn = connect(":memory:")
    apply_schema(conn)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {r["name"] for r in rows}
    assert {
        "plants",
        "observations",
        "diagnoses",
        "roadmap_steps",
        "feedback",
        "user_profile",
        "messages",
    } <= tables


def test_apply_schema_is_idempotent():
    conn = connect(":memory:")
    apply_schema(conn)
    apply_schema(conn)  # must not raise


def test_foreign_keys_are_enforced():
    conn = connect(":memory:")
    apply_schema(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO observations (plant_id, kind, photo_refs, created_at) VALUES (?, ?, ?, ?)",
            (999, "initial", "[]", "2026-01-01T00:00:00+00:00"),
        )


def test_location_kind_is_constrained():
    conn = connect(":memory:")
    apply_schema(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO plants (name, location_kind, created_at) VALUES (?, ?, ?)",
            ("Basil", "orbital", "2026-01-01T00:00:00+00:00"),
        )


def test_transaction_serialises_concurrent_writers_on_one_connection():
    """Two threads writing through ``transaction()`` on the same connection must not
    lose or corrupt each other's rows.

    ``connect()`` sets ``check_same_thread=False`` because the app's one cached
    connection is shared across every browser session, and two sessions' script
    threads can genuinely overlap. Without a lock serialising ``transaction()``, one
    thread's ``commit()``/``rollback()`` could land on the other's still-open
    transaction — this reproduces that contention and asserts every row survives.
    """
    conn = connect(":memory:")
    apply_schema(conn)

    rows_per_thread = 20
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _write(name_prefix: str) -> None:
        barrier.wait()  # start both threads at the same instant
        try:
            with transaction(conn):
                for i in range(rows_per_thread):
                    conn.execute(
                        "INSERT INTO plants (name, location_kind, created_at) VALUES (?, ?, ?)",
                        (f"{name_prefix}-{i}", "indoor", "2026-01-01T00:00:00+00:00"),
                    )
                    # Widen the window: without the lock, the other thread's
                    # commit()/rollback() has room to interleave here.
                    time.sleep(0.001)
        except BaseException as exc:  # captured; asserted on below rather than raised here
            errors.append(exc)

    threads = [threading.Thread(target=_write, args=(f"writer-{n}",)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert not errors, f"a writer raised: {errors}"

    count = conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
    assert count == rows_per_thread * len(threads)
