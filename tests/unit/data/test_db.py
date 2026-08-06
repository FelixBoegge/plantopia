"""Tests for the database connection factory."""

import sqlite3

import pytest

from data.db import apply_schema, connect


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
