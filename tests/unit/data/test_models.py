"""The schema's shape, asserted without a database.

These are metadata assertions, not round-trips: they hold the decisions this change
made — UUID keys, timestamps that carry an offset, ownership on the three tables that
have an owner directly — where a reader can see them fail.
"""

from datetime import datetime

import pytest
from sqlalchemy import DateTime, Uuid

from core.ids import new_id
from data.models import Base

EXPECTED_TABLES = {
    "users",
    "plants",
    "observations",
    "diagnoses",
    "roadmap_steps",
    "feedback",
    "user_profile",
    "messages",
    "profile_cursors",
}

OWNED_DIRECTLY = {"plants", "user_profile", "messages"}


def test_the_schema_holds_exactly_the_expected_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_primary_key_is_a_uuid():
    for name, table in Base.metadata.tables.items():
        for column in table.primary_key.columns:
            assert isinstance(column.type, Uuid), f"{name}.{column.name} is not a UUID"


def test_every_timestamp_carries_an_offset():
    """M3 recorded PARSE_DECLTYPES as a line that read like a guarantee and did nothing,
    because every temporal column was TEXT. A column declared without a timezone would
    reintroduce exactly that gap."""
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone, f"{name}.{column.name} has no timezone"


@pytest.mark.parametrize("table", sorted(OWNED_DIRECTLY))
def test_directly_owned_tables_carry_an_owner(table):
    assert "user_id" in Base.metadata.tables[table].columns


def test_tables_reaching_an_owner_through_a_parent_do_not_carry_one():
    """Ownership is denormalised onto exactly the tables that need it. Adding user_id to
    a child as well would create a second, independently-wrong answer to who owns it."""
    for name in EXPECTED_TABLES - OWNED_DIRECTLY - {"users"}:
        assert "user_id" not in Base.metadata.tables[name].columns, name


def test_a_learned_fact_is_unique_per_owner_not_globally():
    """The SQLite schema's UNIQUE(fact) was correct for exactly one user and silently
    wrong for two: the second person to tend to overwater would have been a conflict."""
    constraints = {
        tuple(sorted(c.columns.keys()))
        for c in Base.metadata.tables["user_profile"].constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }

    assert ("fact", "user_id") in constraints
    assert ("fact",) not in constraints


def test_deleting_an_owner_cascades_to_their_plants():
    fks = list(Base.metadata.tables["plants"].c.user_id.foreign_keys)

    assert [fk.ondelete for fk in fks] == ["CASCADE"]


def test_deleting_a_plant_cascades_to_everything_hanging_off_it():
    for name in ("observations", "diagnoses", "roadmap_steps", "messages", "profile_cursors"):
        fks = list(Base.metadata.tables[name].c.plant_id.foreign_keys)
        assert [fk.ondelete for fk in fks] == ["CASCADE"], name


def test_identifiers_come_from_the_application_not_the_database():
    """Every primary key defaults to a Python-side generator, so no insert depends on a
    database function or on reading a value back.

    Note the timing: a column default fires at flush, not at construction, so a caller
    that needs the identifier *before* the insert — the blob store, whose key is its
    return value — assigns one explicitly. That is the case the next test covers.

    Keys borrowed from a parent are exempt: profile_cursors is keyed by the plant whose
    thread it tracks, so it has nothing of its own to generate."""
    for name, table in Base.metadata.tables.items():
        for column in table.primary_key.columns:
            if column.foreign_keys:
                continue
            default = column.default
            assert default is not None, f"{name}.{column.name} has no default"
            assert default.is_callable, f"{name}.{column.name} defaults to a literal"
            assert default.arg(None).version == 7


def test_an_identifier_can_be_supplied_ahead_of_the_insert():
    from data.models import Plant

    given = new_id()
    plant = Plant(id=given, name="Basil", location_kind="indoor", created_at=datetime.now())

    assert plant.id == given
