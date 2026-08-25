"""Fixtures backed by a real PostgreSQL.

`docker compose up -d db` is a prerequisite for running the suite. The alternative —
mocking the database — would produce tests that assert on the mock, which is precisely
the failure mode worth avoiding in a change whose whole subject is the database.

Tests run against a **separate database**, created once per session and dropped at the
end, so a suite run can never touch development data. Each test runs inside a
transaction that is rolled back afterwards, which is both faster than recreating the
schema per test and stricter: a test that leaks state fails its neighbour rather than
passing quietly.

No LLM call is made from any of this. That constraint is unchanged and absolute.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from core.config import Settings
from data.engine import build_engine, build_sessions
from data.models import Base
from tests.secrets import TEST_JWT_SECRET

TEST_DATABASE = "plantopia_test"


def _urls() -> tuple[str, str]:
    """Return the maintenance URL and the test-database URL.

    A placeholder key is passed because this fixture is session-scoped and therefore
    runs before the autouse fixture that sets one; the database URL is all it wants.
    ``_env_file=None`` is deliberate and matches every other test-side construction —
    M6 records a run where a second key landing in a developer's own .env failed the
    gated suite on their machine and nowhere else.
    """
    configured = make_url(
        Settings(
            _env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET
        ).database_url
    )
    maintenance = configured.set(database="postgres")
    testing = configured.set(database=TEST_DATABASE)
    return maintenance.render_as_string(hide_password=False), testing.render_as_string(
        hide_password=False
    )


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    """An engine on a throwaway database holding the current schema."""
    maintenance_url, test_url = _urls()

    admin = build_engine(maintenance_url)
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    except Exception as exc:  # pragma: no cover - environment failure, not logic
        pytest.fail(
            f"Cannot reach PostgreSQL at {make_url(maintenance_url).set(password=None)}. "
            f"Run `docker compose up -d db` before the suite. Original error: {exc}"
        )
    finally:
        admin.dispose()

    engine = build_engine(test_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()
    admin = build_engine(maintenance_url)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back when the test ends.

    The session joins an outer transaction on a single connection rather than owning
    one, so a ``commit()`` inside the test under test is real to that test and invisible
    to the next one. Without this, testing the commit path would mean either recreating
    the schema per test or leaving rows behind for the next test to trip over.
    """
    connection = pg_engine.connect()
    outer = connection.begin()
    session = build_sessions(pg_engine)(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    outer.rollback()
    connection.close()
