"""SQLite connection factory and schema application."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and dict-like rows.

    ``check_same_thread=False`` because the caller reuses a single connection across
    Streamlit reruns, and Streamlit is free to run a script on a different worker
    thread from one rerun to the next. Access stays serialised regardless — a rerun
    runs to completion before the next begins — so this widens which thread may call
    in, not how many may call concurrently.

    Args:
        path: Database file path, or ``":memory:"`` for an ephemeral database.
    """
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create every table and index. Safe to call repeatedly."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Group repository writes into one atomic unit.

    Commits on success, rolls back on any exception. Repositories deliberately do not
    commit — whether a set of writes is one unit is the caller's decision.

    All repositories participating in one transaction must share this same connection.
    """
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
