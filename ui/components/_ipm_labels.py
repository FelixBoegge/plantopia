"""Owner-facing names for the integrated-pest-management tiers.

Lives in ``ui/`` rather than next to ``IPMTier`` in ``agent/schemas.py`` because these
are presentation strings, not part of the schema contract — the model never sees them.
Shared by ``roadmap.py`` (read-only render of a fresh ``Roadmap``) and
``roadmap_checklist.py`` (persisted, tickable ``RoadmapStepRecord`` rows), which each
carried their own copy keyed differently: one by ``IPMTier``, one by ``int``.

``IPMTier`` is an ``IntEnum``, so a single mapping keyed by the enum serves both — an
``int`` key equal to a member's value hashes and compares equal to that member.
"""

from agent.schemas import IPMTier

TIER_LABEL: dict[IPMTier, str] = {
    IPMTier.CULTURAL: "Adjust conditions",
    IPMTier.MECHANICAL: "Physical treatment",
    IPMTier.BIOLOGICAL: "Biological control",
    IPMTier.CHEMICAL: "Chemical treatment",
}
