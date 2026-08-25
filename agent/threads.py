"""Thread identifiers, and who is allowed to resume one.

A thread id is not a label. It is the handle that resumes a paused diagnosis — one that
has already spent money on vision and reasoning calls, and is holding an owner's
photographs in its state. Anyone who can produce the string can continue the run.

The previous scheme made that a real hazard: a re-check thread was
``recheck-{plant_id}-{diagnosis_id}-{attempt}``, built from three values a second user
could plausibly guess or enumerate. Every handle now carries the owner, and every resume
path checks it before touching state.

Construction and verification live together here so they cannot drift apart — a prefix
added in one page and checked in another is a prefix that eventually stops matching.
"""

from uuid import UUID, uuid4

SEPARATOR = ":"


class ThreadOwnershipError(PermissionError):
    """A thread handle was presented by somebody it does not belong to.

    Callers turn this into "not found" rather than "forbidden": a refusal that
    distinguishes the two confirms the run exists.
    """


def diagnosis_thread(user_id: UUID) -> str:
    """A fresh handle for a first diagnosis.

    Random rather than derived: at the point the wizard starts there is no plant yet,
    and nothing else about the run is stable enough to name it by.
    """
    return f"{user_id}{SEPARATOR}diagnose{SEPARATOR}{uuid4().hex}"


def recheck_thread(user_id: UUID, plant_id: UUID, diagnosis_id: UUID | None, attempt: int) -> str:
    """A handle for re-checking a known plant.

    Derived rather than random, so that returning to a re-check resumes it instead of
    starting a second one. ``attempt`` is what makes an abandoned attempt unreachable
    from the next one (``U7``): neither a rejection nor a retake writes a diagnosis, so
    without it the derived id would not move and the retry would resume the wreckage.
    """
    latest = diagnosis_id or "none"
    parts = (str(user_id), "recheck", str(plant_id), str(latest), str(attempt))
    return SEPARATOR.join(parts)


def chat_thread(user_id: UUID, plant_id: UUID) -> str:
    """The ReAct loop's own thread, distinct from any diagnosis thread for that plant."""
    return f"{user_id}{SEPARATOR}chat{SEPARATOR}{plant_id}"


def owner_of(thread_id: str) -> UUID | None:
    """The owner a handle names, or ``None`` if it names nothing recognisable.

    A malformed handle is not an error here. It is simply not a handle belonging to
    anybody, which is what ``verify_owner`` needs to know.
    """
    head, _, rest = thread_id.partition(SEPARATOR)
    if not rest:
        return None
    try:
        return UUID(head)
    except ValueError:
        return None


def verify_owner(thread_id: str, user_id: UUID) -> None:
    """Raise unless this handle belongs to this owner.

    Called before every resume. The check is cheap and the failure it prevents is
    somebody continuing a stranger's paid run and reading their photographs.
    """
    if owner_of(thread_id) != user_id:
        raise ThreadOwnershipError(f"thread {thread_id!r} does not belong to this owner")


def prefix_for(user_id: UUID) -> str:
    """Everything belonging to one owner starts with this.

    Used to delete an owner's run state: checkpoint rows are keyed by thread id, and the
    prefix is the only thing that relates them back to a person.
    """
    return f"{user_id}{SEPARATOR}"
