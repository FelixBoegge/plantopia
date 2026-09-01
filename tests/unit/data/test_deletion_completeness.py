"""Deleting an account leaves nothing, proven against the schema rather than a list.

The tenancy tests prove one owner cannot *read* another's records. This is the other half,
and it is the harder one to keep true: a read path that misses a table fails visibly the
first time somebody looks, and a delete path that misses one fails silently and forever.

So the enumeration is derived from `Base.metadata` and not written out here. A table added
next year has to be classified before these pass, which is the only version of this check
that survives the person who wrote it.
"""

import pytest
from sqlalchemy import func, select

from data.models import Base
from tests.accounts import populate
from tests.unit.data.test_models import EXPECTED_TABLES, REFERENCE_TABLES

# Every table that holds something belonging to somebody. Derived, not listed: the moment a
# table exists that is neither reference data nor owned, this set is wrong in a way the
# tests below will say out loud.
OWNED_TABLES = EXPECTED_TABLES - REFERENCE_TABLES


def _count(session, table: str) -> int:
    return session.scalar(select(func.count()).select_from(Base.metadata.tables[table]))


def _delete_user(session, user_id) -> None:
    """What the deletion service will do to the application's own tables.

    Deliberately the raw statement rather than the service: this test is about whether the
    *schema* carries deletion all the way down, and running it through the service would
    conflate "the cascades are complete" with "the service calls the right things".
    """
    session.execute(
        Base.metadata.tables["users"].delete().where(Base.metadata.tables["users"].c.id == user_id)
    )
    session.flush()


class TestTheAccountIsGenuinelyFull:
    """A guard on the guard.

    If `populate` stopped filling a table, every deletion assertion below would still pass —
    against an empty table that proves nothing. This is what makes the rest mean something.
    """

    @pytest.mark.parametrize("table", sorted(OWNED_TABLES))
    def test_every_owned_table_has_a_row(self, db, table):
        populate(db)

        assert _count(db, table) > 0, (
            f"tests/accounts.py:populate does not create a row in {table!r}, so no deletion "
            "test can prove that table is cleared. Add one there."
        )

    def test_the_classification_covers_the_schema(self):
        """Inherited from `test_models.py`, restated because this file's correctness rests
        on it: if a table were in neither set, it would be silently exempt from deletion."""
        assert set(Base.metadata.tables) == EXPECTED_TABLES
        assert REFERENCE_TABLES <= EXPECTED_TABLES


class TestNothingOfTheAccountRemains:
    @pytest.mark.parametrize("table", sorted(OWNED_TABLES))
    def test_every_owned_table_is_empty_afterwards(self, db, table):
        account = populate(db)
        assert _count(db, table) > 0

        _delete_user(db, account.user_id)

        assert _count(db, table) == 0, (
            f"{table!r} still holds rows after the account was deleted. Every foreign key "
            "in data/models.py declares ondelete=CASCADE; if this fails, one of them "
            "stopped doing so, or the table reaches its owner by a path the cascade does "
            "not follow."
        )

    @pytest.mark.parametrize(
        "table",
        # The six that carry no `user_id` at all and are reachable only through a parent.
        # Named explicitly as well as covered above, because they are the ones a
        # hand-written "delete where user_id = X" would miss, and the reason this file
        # exists.
        ["observations", "diagnoses", "roadmap_steps", "feedback", "profile_cursors", "run_events"],
    )
    def test_the_tables_with_no_owner_column_go_too(self, db, table):
        assert "user_id" not in Base.metadata.tables[table].columns
        account = populate(db)

        _delete_user(db, account.user_id)

        assert _count(db, table) == 0

    def test_the_photographs_go(self, db):
        """`blobs` carries `user_id` directly, so the cascade covers it — unlike deleting a
        single plant, where nothing relates the bytes to the plant and they are removed by
        hand."""
        account = populate(db)

        _delete_user(db, account.user_id)

        assert _count(db, "blobs") == 0


class TestWhatIsNotDeleted:
    def test_reference_data_is_untouched(self, db):
        """The corpus and the species baselines describe plants, not people. "Delete
        everything with no owner column" would take them, and degrade the system for
        everybody else."""
        account = populate(db)
        _seed_reference_data(db)
        before = {table: _count(db, table) for table in REFERENCE_TABLES}
        assert all(count > 0 for count in before.values())

        _delete_user(db, account.user_id)

        assert {table: _count(db, table) for table in REFERENCE_TABLES} == before

    def test_another_owner_is_left_exactly_as_they_were(self, db):
        """Snapshot, add a second account, delete it, compare.

        Stronger than checking the survivor still has rows, and simpler: the counts must
        return to *exactly* what they were. That proves both halves at once — every row of
        the deleted account is gone, and not one row of the survivor's went with it —
        without this test needing to know how any table reaches its owner.
        """
        populate(db)
        _seed_reference_data(db)
        before = {table: _count(db, table) for table in sorted(EXPECTED_TABLES)}

        doomed = populate(db)
        assert {table: _count(db, table) for table in sorted(OWNED_TABLES)} != {
            table: before[table] for table in sorted(OWNED_TABLES)
        }, "the second account added nothing, so this proves nothing"

        _delete_user(db, doomed.user_id)

        assert {table: _count(db, table) for table in sorted(EXPECTED_TABLES)} == before


def _seed_reference_data(session) -> None:
    """A corpus chunk and a researched care profile, so "unchanged" has something to say."""
    from datetime import UTC, datetime

    from agent.schemas import CareOrigin, CareProfile
    from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
    from data.repositories.care_profiles import CareProfileRepository

    session.add(
        CorpusChunk(
            doc_id="overwatering",
            section="symptoms",
            name="Overwatering",
            content="Lower leaves yellow and the soil stays wet.",
            category="watering",
            transmissible=False,
            severity="act_this_week",
            embedding=[0.0] * EMBEDDING_DIMENSIONS,
        )
    )
    CareProfileRepository(session).put(
        CareProfile(
            species="Calathea orbifolia",
            light="Bright indirect",
            water="Evenly moist",
            temperature_c=(18, 24),
            humidity="Above 60 percent",
            origin=CareOrigin.RESEARCHED,
            sources=["web:example.test"],
        ),
        now=datetime(2026, 3, 1, tzinfo=UTC),
    )
    session.flush()
