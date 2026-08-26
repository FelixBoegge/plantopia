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
    "blobs",
    "corpus_chunks",
    "refresh_tokens",
    "email_tokens",
    "usage_events",
    "runs",
    "run_events",
}

OWNED_DIRECTLY = {
    "plants",
    "user_profile",
    "messages",
    "blobs",
    "refresh_tokens",
    "email_tokens",
    "usage_events",
    "runs",
}

# Reference data, not records. The corpus is the same for everyone, so it has no owner,
# no cascade, and a natural key — (doc_id, section) *is* its identity, and it is what
# fetch-by-id looks a passage up by. The rules below about UUID keys and generated
# identifiers exist to stop enumeration of a person's records; neither applies here.
REFERENCE_TABLES = {"corpus_chunks"}


def test_the_schema_holds_exactly_the_expected_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_record_table_has_a_uuid_primary_key():
    """The point is enumeration: /plants/3 tells a stranger how many plants exist. A
    corpus section has no such secret, and its key is its meaning."""
    for name, table in Base.metadata.tables.items():
        if name in REFERENCE_TABLES:
            continue
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
    for name in EXPECTED_TABLES - OWNED_DIRECTLY - REFERENCE_TABLES - {"users"}:
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
        if name in REFERENCE_TABLES:
            continue
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


def test_the_corpus_is_not_owned_by_anyone():
    """A shared corpus with a user_id would be 43 documents per account."""
    assert "user_id" not in Base.metadata.tables["corpus_chunks"].columns


def test_the_corpus_embedding_column_has_no_index():
    """An approximate index can reorder results by construction, which would make the
    parity gate unable to attribute a difference to the new SQL. 301 rows scan in
    under a millisecond; revisit at an order of magnitude more."""
    assert Base.metadata.tables["corpus_chunks"].indexes == set()


def test_a_password_is_never_stored_recoverably():
    """There is exactly one password column and it holds a hash. Asserted structurally so
    that a future "password_plain" or "password_hint" fails here rather than in a breach."""
    columns = set(Base.metadata.tables["users"].columns.keys())
    password_columns = {c for c in columns if "password" in c}

    assert password_columns == {"password_hash"}


def test_tokens_sent_by_email_are_stored_hashed():
    """A stolen database must not yield a working reset link for every account in it."""
    for table in ("refresh_tokens", "email_tokens"):
        columns = set(Base.metadata.tables[table].columns.keys())
        assert "token_hash" in columns, table
        assert "token" not in columns, f"{table} stores a token in the clear"


def test_a_refresh_token_belongs_to_a_family():
    """Reuse detection invalidates everything descended from one sign-in, which is only
    possible if the descent is recorded."""
    assert "family_id" in Base.metadata.tables["refresh_tokens"].columns


def test_usage_distinguishes_unknown_cost_from_zero():
    """An unmeasured run must not be readable as a free one."""
    assert Base.metadata.tables["usage_events"].c.cost_usd.nullable


def test_a_runs_sequence_is_unique_within_its_run_and_not_globally():
    """Two concurrent runs must not interleave, and a global counter would make the
    replay query a scan across everybody's events."""
    constraint = next(
        c
        for c in Base.metadata.tables["run_events"].constraints
        if c.name == "uq_run_events_sequence"
    )

    assert {column.name for column in constraint.columns} == {"run_id", "sequence"}


def test_a_run_records_when_its_status_last_changed_separately_from_when_it_started():
    """Both ceilings measure from the status change. A run that waited an hour for
    answers has not been working for an hour, and one clock cannot say both."""
    columns = Base.metadata.tables["runs"].columns

    assert "created_at" in columns
    assert "status_changed_at" in columns


def test_an_account_carries_a_role():
    """Distinct from a tier. One decides what may be reached, the other what may be spent,
    and conflating them would make an allowance an access rule."""
    columns = Base.metadata.tables["users"].columns

    assert "role" in columns
    assert "tier" in columns


def test_a_role_the_application_does_not_recognise_is_refused_by_the_schema():
    """A column with two legal values and a constraint that says so. Application code is
    not the only thing that writes to this table."""
    constraint = next(
        c
        for c in Base.metadata.tables["users"].constraints
        if getattr(c, "name", None) == "ck_users_role"
    )

    assert "member" in str(constraint.sqltext)
    assert "admin" in str(constraint.sqltext)
