"""What a client is told a run is doing.

A mapping from the graph's node names to a stable event kind and a sentence somebody can
read. It exists so that the graph's internal structure is not part of the public interface:
a client rendering ``identify_plant`` is a client coupled to a function name, and renaming
that function then becomes a breaking change to the API.

**The map is total, and a test enforces it.** A node with no entry produces a neutral event
rather than falling back to its own name — a fallback that leaks the internal name leaks it
exactly when somebody has added a node and forgotten this file, which is the only occasion
it would ever matter.
"""

from dataclasses import dataclass

# Event kinds a client may branch on. Distinct from the step identifiers below: these say
# what *sort* of thing happened, where a step says which one.
#
# One vocabulary for runs and for chat, so a frontend learns it once. A diagnosis and a
# chat reply are different work, but "something is happening", "a source was consulted" and
# "this is how it ended" are the same three things to whatever is drawing a screen.
STEP = "step"
QUESTIONS = "questions"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

# Chat also uses these two. A run has no use for them: its steps are named stages, and it
# produces a diagnosis rather than prose.
TOOL = "tool"
DELTA = "delta"


@dataclass(frozen=True, slots=True)
class Step:
    """One stage of a run, as a client sees it."""

    id: str
    description: str


# Keyed by node name, which is the only place a node name appears outside the graph.
STEPS: dict[str, Step] = {
    "guard_input": Step("checking", "Checking the photographs"),
    "quality_check": Step("checking", "Checking the photographs"),
    "identify_plant": Step("identifying", "Identifying the species"),
    "assess_symptoms": Step("examining", "Looking at what the leaves are doing"),
    "select_questions": Step("preparing_questions", "Working out what else to ask"),
    "gather_context": Step("reading_answers", "Reading your answers"),
    "hypothesise": Step("considering", "Considering what this could be"),
    "enrich": Step("consulting", "Consulting the disorder reference"),
    "diagnose": Step("diagnosing", "Weighing the evidence"),
    "check_contagion": Step("checking_spread", "Checking whether it spreads"),
    "build_roadmap": Step("planning", "Putting together a plan"),
    "persist": Step("saving", "Saving the result"),
    "compare_progress": Step("comparing", "Comparing against the last diagnosis"),
    "revise_roadmap": Step("revising", "Updating the plan"),
}

# What an unmapped node produces. Deliberately says nothing specific: a run still reports
# progress, and nobody learns a function name from it.
UNKNOWN = Step("working", "Working")


def step_for(node: str) -> Step:
    """The step a node corresponds to."""
    return STEPS.get(node, UNKNOWN)


# Settings attributes that name a model. Anything in CALLS that is not one of these is the
# name of an outside service, written as somebody should read it.
MODEL_ROLES = frozenset({"gate_model", "vision_model", "reasoning_model"})

# What each node reaches for, in the order it reaches for it.
#
# Deliberately beside STEPS and keyed the same way: a node whose work changes needs both
# entries updated, and having them adjacent is the only thing that makes that likely.
#
# Nodes that call neither a model nor a service are absent rather than present and empty —
# `persist` writes rows and `compare_progress` reads them, and naming a service for either
# would describe work that does not happen.
CALLS: dict[str, tuple[str, ...]] = {
    "guard_input": ("gate_model",),
    "quality_check": ("gate_model",),
    "identify_plant": ("vision_model", "Pl@ntNet"),
    "assess_symptoms": ("vision_model",),
    "select_questions": ("reasoning_model", "OpenStreetMap"),
    "hypothesise": ("reasoning_model",),
    "enrich": ("the disorder reference", "Open-Meteo"),
    "diagnose": ("reasoning_model",),
    "check_contagion": ("reasoning_model",),
    "build_roadmap": ("reasoning_model",),
    "revise_roadmap": ("reasoning_model",),
}


def calls_for(node: str, settings) -> str | None:
    """What this node called, in words, or ``None`` where it called nothing outside.

    A model is named from ``settings`` rather than written out here, so the sentence follows
    the configuration instead of describing whichever model happened to be current when this
    was typed.
    """
    parts = CALLS.get(node)
    if not parts:
        return None
    return ", then ".join(
        f"{getattr(settings, part)} via OpenRouter" if part in MODEL_ROLES else part
        for part in parts
    )
