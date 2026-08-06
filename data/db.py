"""SQLite connection factory and schema application."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Serialises transaction() across threads sharing one connection (see its docstring).
# Module-level and unkeyed by connection: the app only ever has one connection alive
# at a time in practice (one process, one cached DiagnosisService), so one lock is
# simpler than a per-connection registry and no less correct for that shape.
_write_lock = threading.Lock()


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and dict-like rows.

    ``check_same_thread=False`` because the caller reuses a single connection across
    Streamlit reruns, and ``ui.bootstrap.get_service`` caches it process-wide with
    ``@st.cache_resource`` and no session key — every browser session shares it.
    Streamlit reruns are serialised *within* one session, but two tabs against the
    same server are independent script threads that can genuinely overlap, so this
    flag alone only fixes *which* thread may use the connection, not how many may use
    it at once. ``transaction()`` below is what provides the latter guarantee.

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
    """Group repository writes into one atomic unit, safe under concurrent callers.

    Commits on success, rolls back on any exception. Repositories deliberately do not
    commit — whether a set of writes is one unit is the caller's decision.

    Also serialises access to ``conn`` across threads: SQLite's implicit-transaction
    state lives on the connection, not the thread, so without a lock one thread's
    ``commit()``/``rollback()`` could land on another thread's still-open transaction
    — committing half-written work or rolling back a legitimate one. The module-level
    lock makes each ``transaction()`` block atomic against concurrent callers on the
    same connection, in addition to atomic against failure.

    All repositories participating in one transaction must share this same connection.
    """
    with _write_lock:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
