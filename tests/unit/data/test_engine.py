"""The unit of work: writes land together, or not at all."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from data.engine import transaction
from data.models import Plant
from tests.people import make_user


def _owner(session):
    return make_user(session)


def _plant(owner, name, *, location_kind="indoor"):
    return Plant(
        user_id=owner.id,
        name=name,
        location_kind=location_kind,
        created_at=datetime.now(UTC),
    )


def test_a_completed_block_commits_its_writes(pg_session):
    owner = _owner(pg_session)

    with transaction(pg_session) as session:
        session.add(_plant(owner, "Basil"))

    assert pg_session.scalars(select(Plant).where(Plant.user_id == owner.id)).all()


def test_an_exception_rolls_the_whole_block_back(pg_session):
    """Both plants go, not just the one after the failure — persist writes a plant, an
    observation, a diagnosis and its roadmap steps as one unit, and a half-written
    diagnosis in the timeline is worse than no diagnosis."""
    owner = _owner(pg_session)

    with (
        pytest.raises(RuntimeError, match="the model fell over"),
        transaction(pg_session) as session,
    ):
        session.add(_plant(owner, "Basil"))
        session.flush()
        session.add(_plant(owner, "Monstera"))
        raise RuntimeError("the model fell over")

    assert pg_session.scalars(select(Plant).where(Plant.user_id == owner.id)).all() == []


def test_the_original_exception_survives_the_rollback(pg_session):
    """A rollback that swallowed the cause would leave the caller unable to tell a
    failed diagnosis from an empty one."""
    with pytest.raises(ValueError, match="specific cause"), transaction(pg_session):
        raise ValueError("specific cause")


def test_the_check_constraints_are_enforced_by_the_database(pg_session):
    """The location check is in the schema, not only in the application, so a write
    that bypasses the service layer still cannot store nonsense."""
    from sqlalchemy.exc import IntegrityError

    owner = _owner(pg_session)

    with pytest.raises(IntegrityError), transaction(pg_session) as session:
        session.add(_plant(owner, "Basil", location_kind="orbital"))
