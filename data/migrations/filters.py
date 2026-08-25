"""What autogenerate is allowed to look at.

Its own module rather than living in ``env.py``, because ``env.py`` can only be imported
inside an Alembic run — and the test that asserts the models and the migrations agree has
to apply exactly these rules or it compares a different thing than the tool does.
"""

# Tables LangGraph's Postgres checkpointer creates and owns. They live in the same
# database and are not in ``Base.metadata``, so autogenerate reads them as ours and gone,
# and writes a migration that drops the checkpoints every in-flight run resumes from.
#
# Matched by prefix rather than listed exactly: the set has changed across LangGraph
# versions, and a list that goes stale fails in the destructive direction.
FOREIGN_TABLE_PREFIXES = ("checkpoint",)


def _is_ours(name: str | None, type_: str) -> bool:
    """Whether Alembic should consider an object at all.

    Applies to tables and to what hangs off them: an index on a foreign table is as much
    somebody else's as the table is.
    """
    if type_ not in {"table", "index", "unique_constraint", "foreign_key_constraint"}:
        return True
    if name is None:
        return True
    return not name.startswith(FOREIGN_TABLE_PREFIXES)


def include_name(name, type_, parent_names) -> bool:
    """Filters what autogenerate *reflects* from the database."""
    if type_ == "table":
        return _is_ours(name, "table")
    return True


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Filters what autogenerate *compares*, including indexes on foreign tables."""
    if type_ == "table":
        return _is_ours(name, "table")
    parent = getattr(getattr(obj, "table", None), "name", None)
    return parent is None or _is_ours(parent, "table")
