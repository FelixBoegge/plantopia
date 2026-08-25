"""The engine, sessions, and the unit of work.

Replaces what ``data/db.py`` did for SQLite. Two things that file needed disappear here,
and both are worth naming because their absence is the point.

**The module-level write lock is gone.** ``data.db`` serialised every ``transaction()``
across threads because SQLite keeps implicit-transaction state on the *connection*, so
one thread's commit could land on another thread's open transaction — and because a
SQLite database file has a single write lock regardless of how many connections address
it. Postgres has neither problem: each session holds its own connection, transactions
are per-connection, and concurrent writers are resolved by MVCC rather than by waiting.
Keeping the lock would serialise writers that the database is perfectly willing to run
at once.

**Schema application is gone.** ``apply_schema`` executed a .sql file on every connect,
which works exactly once — the first time a database is created — and has no answer for
a column added later. Alembic owns the schema now.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(url: str, *, echo: bool = False) -> Engine:
    """Open a connection pool.

    ``pool_pre_ping`` costs a round-trip on checkout and buys correctness across a
    database restart: without it, the first query after the container comes back gets a
    connection the pool believes is live and the application sees an operational error
    it did nothing to cause.

    Args:
        url: A SQLAlchemy URL naming its driver — ``postgresql+psycopg://…``. A bare
            ``postgresql://`` resolves to psycopg2, which this project does not install.
        echo: Log every statement. For debugging a query, never for normal running.
    """
    return create_engine(url, echo=echo, pool_pre_ping=True)


def build_sessions(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to ``engine``.

    ``expire_on_commit=False`` because callers read attributes off a record after the
    transaction that wrote it has closed — the repositories return plain records, and
    re-fetching each one on attribute access would turn a returned list into a query per
    row.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Group writes into one atomic unit.

    Commits on success, rolls back on any exception, and re-raises. Repositories
    deliberately do not commit: whether a set of writes is one unit is the caller's
    decision, and ``agent/nodes/persist.py`` depends on that — a plant, an observation,
    a diagnosis and its roadmap steps are written together or not at all.
    """
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
