"""Where paused runs live.

Both graphs share one Postgres checkpointer. They used to have a SQLite file each, and
the reason was ``M15``: diagnosis state carried whole photographs as base64, so its
checkpoint file grew by ~100 MB per run and had no business sharing a file with a chat
transcript. State carries keys now, so that reason is gone — and thread ids keep the two
apart by construction (``agent.threads``).

The tables belong to LangGraph, not to this project's schema, so Alembic does not own
them: ``PostgresSaver.setup()`` creates and migrates its own. That is why deleting an
owner's run state is a query here rather than a cascade — nothing relates a checkpoint
row to a user except the prefix on its thread id.
"""

import logging
from functools import lru_cache
from uuid import UUID

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from agent.threads import prefix_for
from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# LangGraph keys all three by thread_id. checkpoint_migrations is its own bookkeeping and
# has no thread column.
_THREAD_KEYED_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


def checkpointer_url(settings: Settings | None = None) -> str:
    """The database URL in the form psycopg wants.

    SQLAlchemy's URL names its driver (``postgresql+psycopg://``); psycopg does not
    understand that suffix, and the failure is an unhelpful parse error rather than
    anything naming the URL.
    """
    settings = settings or get_settings()
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache(maxsize=1)
def _pool(url: str) -> ConnectionPool:
    """One pool for checkpoint traffic, separate from the application's.

    Separate because the checkpointer holds a connection for the length of a graph
    invocation — up to ninety seconds of model calls — and starving ordinary queries
    behind that is not a trade worth making.
    """
    return ConnectionPool(url, min_size=1, max_size=4, open=True, kwargs={"autocommit": True})


@lru_cache(maxsize=1)
def build_checkpointer(url: str) -> PostgresSaver:
    """A checkpointer, with its tables created on first use.

    ``setup()`` is idempotent and cheap after the first call, and calling it here rather
    than in a deployment script means a fresh database cannot start the application in a
    state where the first diagnosis fails on a missing table.
    """
    saver = PostgresSaver(_pool(url))
    saver.setup()
    return saver


def delete_thread(url: str, thread_id: str) -> int:
    """Remove one conversation's checkpoints. Returns rows deleted.

    An exact match rather than the prefix `delete_for_user` uses: this removes one thread,
    not everything belonging to whoever owns it. Written for plant deletion, whose spec says
    the plant "and everything hanging off it" is removed and which was leaving the chat
    history behind — invisible, because nothing reads a checkpoint whose plant is gone.
    """
    deleted = _delete_where(url, "thread_id = %s", (thread_id,))
    logger.info("removed %d checkpoint rows for one conversation", deleted)
    return deleted


def delete_for_user(url: str, user_id: UUID) -> int:
    """Remove every checkpoint belonging to one owner. Returns rows deleted.

    Matched on the thread-id prefix, which is the only thing tying a checkpoint to a
    person. ``LIKE`` with an escaped prefix rather than a pattern built by hand: a UUID
    contains no wildcard characters, but the day a thread id includes something else,
    this should not quietly start matching other owners' rows.
    """
    prefix = prefix_for(user_id)
    escaped = prefix.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    deleted = _delete_where(url, "thread_id LIKE %s ESCAPE '!'", (escaped,))
    logger.info("removed %d checkpoint rows for one owner", deleted)
    return deleted


def _delete_where(url: str, condition: str, parameters: tuple) -> int:
    """Delete matching rows from each thread-keyed table, tolerating tables that are absent.

    **The tables may genuinely not exist.** LangGraph creates them in `PostgresSaver.setup()`,
    which runs when a checkpointer is first built — that is, on the first diagnosis. A
    deployment where nobody has run one yet has no checkpoint tables at all, and an account
    deleted before then would otherwise fail with `UndefinedTable` and a 500.

    Found by a browser test deleting a freshly registered account, which is exactly the
    case: sign up, change your mind, and the deletion blows up on tables that only exist
    once somebody has used the thing.

    Each table gets its own transaction block, because a failed statement poisons the
    connection for everything after it — so catching the error without one would turn a
    single missing table into every later table failing too.
    """
    deleted = 0
    with _pool(url).connection() as conn:
        for table in _THREAD_KEYED_TABLES:
            try:
                with conn.transaction(), conn.cursor() as cursor:
                    cursor.execute(f"DELETE FROM {table} WHERE {condition}", parameters)  # noqa: S608
                    deleted += cursor.rowcount
            except psycopg.errors.UndefinedTable:
                # Nothing has ever been checkpointed here. Zero rows removed is the honest
                # answer, and it is the same answer as an account that ran nothing.
                logger.debug("no %s table; nothing to remove from it", table)
    return deleted
