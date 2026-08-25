"""SQLite connections for the LangGraph checkpoint files.

What remains of this module after the domain data moved to Postgres. The two graph
checkpointers are still ``SqliteSaver``, and they are moved in the change's checkpointer
group; this file goes with them.

The schema application and the module-level write lock that used to live here are gone.
Alembic owns the schema, and Postgres resolves concurrent writers without help.
"""

import sqlite3
from pathlib import Path


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a checkpoint-file connection usable from more than one thread.

    ``check_same_thread=False`` because Streamlit reruns are serialised within a
    session but two browser sessions are independent script threads that can genuinely
    overlap.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
