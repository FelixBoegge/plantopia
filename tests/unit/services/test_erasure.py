"""Erasing an account.

`tests/unit/data/test_deletion_completeness.py` proves the *schema* carries a deletion all
the way down. This proves the *service* does the two things the schema cannot see, and does
them in the order that makes the survivable failure the possible one.
"""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from core.config import Settings
from data.models import Base, RefreshToken, User
from data.repositories.errors import RecordNotFoundError
from services import erasure
from tests.accounts import populate
from tests.secrets import TEST_JWT_SECRET


@pytest.fixture
def settings() -> Settings:
    return Settings(jwt_secret=TEST_JWT_SECRET, openai_api_key="x", _env_file=None)


def _count(session, table: str) -> int:
    return session.scalar(select(func.count()).select_from(Base.metadata.tables[table]))


class TestWhatItRemoves:
    def test_the_account_is_gone(self, db, settings, monkeypatch):
        _no_checkpoints(monkeypatch)
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert db.get(User, account.user_id) is None

    def test_everything_hanging_off_it_goes(self, db, settings, monkeypatch):
        """One statement, seventeen tables. Only trustworthy because the completeness test
        enumerates them from `Base.metadata` rather than from a list."""
        _no_checkpoints(monkeypatch)
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        for table in ("plants", "observations", "diagnoses", "messages", "blobs", "runs"):
            assert _count(db, table) == 0, table

    def test_the_sessions_are_revoked(self, db, settings, monkeypatch):
        """So the session cannot be extended past the deletion. `populate` issues one."""
        _no_checkpoints(monkeypatch)
        account = populate(db)
        assert _count(db, "refresh_tokens") > 0

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert _count(db, "refresh_tokens") == 0

    def test_the_revocation_happens_before_the_cascade_takes_the_rows(
        self, db, settings, monkeypatch
    ):
        """Not merely "the rows are gone", which the cascade would achieve on its own.

        Revoking marks the tokens as revoked while they still exist; the cascade then
        deletes them. If the service stopped revoking, this row count would be identical
        and the sessions would have been ended only by the row disappearing — which is the
        same outcome here and a different one anywhere the token is checked without its row.
        """
        seen = []
        monkeypatch.setattr(
            erasure.sessions,
            "revoke_all_for_user",
            lambda session, user_id: seen.append(user_id) or 0,
        )
        _no_checkpoints(monkeypatch)
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert seen == [account.user_id]

    def test_the_checkpoints_go(self, db, settings, monkeypatch):
        asked = []
        monkeypatch.setattr(
            erasure.checkpoints,
            "delete_for_user",
            lambda url, user_id: asked.append(user_id) or 0,
        )
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert asked == [account.user_id]


class TestTheOrder:
    def test_checkpoints_are_removed_before_the_user_row(self, db, settings, monkeypatch):
        """The decision recorded in the service's docstring, pinned.

        Checkpoints live on the checkpointer's own connection and cannot join this
        transaction, so one of the two orders leaves a mess when the other half fails.
        Checkpoints first leaves an account whose history is gone — visible, and somebody
        can complain. The reverse leaves checkpoint rows keyed to a user who no longer
        exists: unreachable by any prefix, and never cleaned up.
        """
        order: list[str] = []

        def _checkpoint_sweep(url: str, user_id: UUID) -> int:
            order.append("checkpoints")
            # The user must still exist at this point, which is the whole property.
            assert db.get(User, user_id) is not None
            return 0

        monkeypatch.setattr(erasure.checkpoints, "delete_for_user", _checkpoint_sweep)
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)
        order.append("user")

        assert order == ["checkpoints", "user"]


class TestWhenItRefuses:
    def test_an_unknown_account(self, db, settings, monkeypatch):
        _no_checkpoints(monkeypatch)

        with pytest.raises(RecordNotFoundError):
            erasure.delete_account(db, user_id=UUID(int=0), settings=settings)

    def test_nothing_is_touched_when_the_account_is_unknown(self, db, settings, monkeypatch):
        _no_checkpoints(monkeypatch)
        populate(db)
        before = _count(db, "plants")

        with pytest.raises(RecordNotFoundError):
            erasure.delete_account(db, user_id=UUID(int=0), settings=settings)

        assert _count(db, "plants") == before

    @pytest.mark.parametrize("failing", ["revoke_all_for_user", "delete_for_user"])
    def test_a_failure_before_the_delete_leaves_the_account_whole(
        self, db, settings, monkeypatch, failing
    ):
        """Both steps that precede the delete, each broken in turn.

        The delete is the last thing the service does, so any earlier failure means it never
        ran and the account is untouched. Asserted inside the same transaction rather than
        after a rollback: rolling back here would undo the fixture's own setup and prove
        nothing about the service.
        """
        _no_checkpoints(monkeypatch)
        account = populate(db)
        before = _count(db, "plants")

        def _explode(*args, **kwargs):
            raise RuntimeError("this dependency fell over")

        target = erasure.sessions if failing == "revoke_all_for_user" else erasure.checkpoints
        monkeypatch.setattr(target, failing, _explode)

        with pytest.raises(RuntimeError):
            erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert db.get(User, account.user_id) is not None
        assert _count(db, "plants") == before

    def test_the_delete_is_the_last_thing_it_does(self, db, settings, monkeypatch):
        """Which is what makes the test above meaningful: if the user row went first, an
        earlier-failing dependency would leave a half-deleted account and the assertions
        above would be describing an ordering the service no longer has."""
        order: list[str] = []
        monkeypatch.setattr(
            erasure.sessions,
            "revoke_all_for_user",
            lambda session, user_id: order.append("revoke") or 0,
        )
        monkeypatch.setattr(
            erasure.checkpoints,
            "delete_for_user",
            lambda url, user_id: order.append("checkpoints") or 0,
        )
        account = populate(db)

        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        assert order == ["revoke", "checkpoints"]
        assert db.get(User, account.user_id) is None


class TestAnotherOwner:
    def test_is_untouched(self, db, settings, monkeypatch):
        _no_checkpoints(monkeypatch)
        doomed = populate(db)
        survivor = populate(db)

        erasure.delete_account(db, user_id=doomed.user_id, settings=settings)

        assert db.get(User, survivor.user_id) is not None
        assert _count(db, "plants") == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(RefreshToken)
                .where(RefreshToken.user_id == survivor.user_id)
            )
            > 0
        )


def _no_checkpoints(monkeypatch) -> None:
    """Stand in for the checkpoint sweep.

    It runs against the checkpointer's own pool — a real connection to a real database,
    outside this test's transaction — so a unit test that let it run would write to, and
    then delete from, tables no fixture rolls back. Its own behaviour is covered by
    `tests/unit/agent/test_checkpoints.py`.
    """
    monkeypatch.setattr(erasure.checkpoints, "delete_for_user", lambda url, user_id: 0)


class TestSigningInAfterwards:
    def test_it_is_refused_the_same_way_as_an_address_that_never_existed(
        self, db, settings, monkeypatch
    ):
        """The identity spec already requires that the system does not reveal who has an
        account. A deleted address must not become distinguishable from an unknown one —
        which would turn deletion into a way to enumerate former users.
        """
        from identity.accounts import AuthenticationError, authenticate

        _no_checkpoints(monkeypatch)
        account = populate(db)
        erasure.delete_account(db, user_id=account.user_id, settings=settings)

        with pytest.raises(AuthenticationError) as deleted:
            authenticate(db, email=account.email, password=account.password)
        with pytest.raises(AuthenticationError) as never_existed:
            authenticate(db, email="nobody@example.test", password=account.password)

        assert str(deleted.value) == str(never_existed.value)
