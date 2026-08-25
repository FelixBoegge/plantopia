"""Alembic's entry point.

The connection URL is not read from alembic.ini. It comes from ``Settings``, the same
place the application reads it, so a migration can never be applied to a different
database than the one the code is about to talk to — which is the whole failure mode a
second copy of a connection string exists to cause.
"""

from logging.config import fileConfig

from alembic import context

from core.config import Settings
from data.engine import build_engine
from data.migrations.filters import include_name, include_object
from data.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout rather than running it, for review or for a DBA."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        include_name=include_name,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = build_engine(_url())

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                include_name=include_name,
                include_object=include_object,
                # Without this, `alembic check` ignores a column whose type changed —
                # which would let the models and the schema drift apart in exactly the
                # way this project has no second source of truth to catch.
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
