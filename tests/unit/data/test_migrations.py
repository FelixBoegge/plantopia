"""The migrations, run the way a clean clone runs them.

Every other test builds its schema with ``Base.metadata.create_all`` — fast, and completely
blind to the migrations. The consequence showed up here: a migration shipped that dropped
LangGraph's checkpoint tables, which destroys every in-flight run on a database that has
them and fails outright on one that does not. The development database had already been
through it, so running `alembic upgrade head` by hand said nothing.

Two things are asserted, and they are different questions:

1. `alembic upgrade head` completes on an empty database. Somebody cloning the repository
   can set it up at all.
2. What the migrations produce matches what the models declare. The two are separate
   sources of truth and this is the only thing comparing them.
"""

import os
import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url

from data.engine import build_engine
from data.migrations.filters import include_name, include_object
from data.models import Base
from tests.postgres import _urls
from tests.secrets import TEST_JWT_SECRET

MIGRATED_DATABASE = "plantopia_migrations_test"


@pytest.fixture(scope="module")
def migrated_url() -> Iterator[str]:
    """A genuinely empty database, brought up to head by the migrations alone."""
    maintenance_url, _ = _urls()
    url = make_url(maintenance_url).set(database=MIGRATED_DATABASE)
    target = url.render_as_string(hide_password=False)

    admin = build_engine(maintenance_url)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATED_DATABASE}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{MIGRATED_DATABASE}"'))
    admin.dispose()

    # ``env.py`` reads the URL from ``Settings``, not from alembic.ini — deliberately, so
    # a migration cannot be applied to a different database than the code will talk to.
    # Pointing the environment at the throwaway one is therefore the only way to redirect
    # it, and setting ``sqlalchemy.url`` would silently migrate the development database.
    #
    # It builds ``Settings()`` bare, so it needs the two fields that have no default as
    # well. This fixture is module-scoped and therefore runs *before* the function-scoped
    # autouse fixture that supplies them — the same ordering `tests/postgres._urls` records.
    # Without them these tests passed only on a machine with a real `.env`, and failed on
    # the first machine without one. That is precisely the failure `M6` describes, and CI
    # found it on its first run.
    environment = {
        "PLANTOPIA_DATABASE_URL": target,
        "PLANTOPIA_OPENROUTER_API_KEY": "sk-test",
        "PLANTOPIA_JWT_SECRET": TEST_JWT_SECRET,
    }
    previous = {name: os.environ.get(name) for name in environment}
    os.environ.update(environment)
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        for name, was in previous.items():
            if was is None:
                del os.environ[name]
            else:
                os.environ[name] = was

    yield target

    admin = build_engine(maintenance_url)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATED_DATABASE}" WITH (FORCE)'))
    admin.dispose()


def test_the_migrations_run_on_an_empty_database(migrated_url):
    """The fixture is the assertion: reaching here means `alembic upgrade head` completed
    from nothing. It did not, before this test existed — a migration dropped an index that
    only exists once LangGraph has run.
    """
    assert migrated_url


def test_the_migrated_schema_holds_every_table_the_models_declare(migrated_url):
    engine = build_engine(migrated_url)
    try:
        with engine.connect() as conn:
            found = set(MigrationContext.configure(conn).connection.dialect.get_table_names(conn))
    finally:
        engine.dispose()

    missing = set(Base.metadata.tables) - found
    assert missing == set(), f"the migrations never create: {sorted(missing)}"


def test_the_migrations_and_the_models_do_not_disagree(migrated_url):
    """`alembic check` as a test, so drift fails a run rather than waiting to be noticed.

    Filtered by the same rules `env.py` uses, so LangGraph's tables are neither expected
    here nor reported as ours to remove.
    """
    engine = build_engine(migrated_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "include_name": include_name,
                    "include_object": include_object,
                    "target_metadata": Base.metadata,
                },
            )
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == [], f"models and migrations disagree: {differences}"


def test_no_migration_touches_a_table_this_project_does_not_own(migrated_url):
    """LangGraph creates and owns the checkpoint tables. A migration that drops one
    deletes the checkpoints every paused run resumes from — and this project's runs pause
    by design, in the middle, after the expensive half.
    """
    versions = pathlib.Path("data/migrations/versions")
    offenders = [
        path.name
        for path in versions.glob("*.py")
        if "checkpoint" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], (
        f"{offenders} reference LangGraph's checkpoint tables. Autogenerate reads them as "
        "ours because they are not in Base.metadata; env.py filters them out, so a "
        "migration mentioning one was generated before that filter existed."
    )
