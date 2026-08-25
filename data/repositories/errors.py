"""What a repository raises when a record is not the caller's to touch.

Reads return ``None`` for a record that is absent *or* belongs to somebody else — the
two are deliberately indistinguishable, because a distinguishable refusal confirms the
record exists.

Writes cannot do that. A write that quietly changes nothing looks identical to a write
that succeeded, and the caller has no way to report the truth to the person who asked.
So writes raise, and the layer above turns that into "not found" — never "forbidden",
which would leak the same fact a refusal does.

Inherits from ``ValueError`` so that ``RoadmapRepository.mark``'s existing contract —
raise on an unknown step id, added when M10 recorded that it silently no-opped — keeps
working for callers that already catch ValueError.
"""


class RecordNotFoundError(ValueError):
    """The record does not exist, or does not belong to this owner."""
