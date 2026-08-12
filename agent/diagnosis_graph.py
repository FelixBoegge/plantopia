"""Assembly of the diagnosis graph.

The pipeline is an explicit state machine rather than a free-form agent loop because
two orderings must be guaranteed: species identification precedes diagnosis, and the
clarifying-question interrupt always fires. A ReAct agent asked to do this reliably
will sometimes skip a step, which would make the human-in-the-loop requirement a
matter of luck.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from agent.deps import Deps
from agent.nodes.context import make_gather_context, make_select_questions
from agent.nodes.diagnose import make_diagnose
from agent.nodes.enrich import make_enrich
from agent.nodes.identify import make_identify_plant
from agent.nodes.intake import make_guard_input, make_quality_check
from agent.nodes.persist import make_persist
from agent.nodes.plan import make_build_roadmap, make_check_contagion
from agent.nodes.recheck import make_compare_progress, make_revise_roadmap
from agent.nodes.symptoms import make_assess_symptoms
from agent.state import DiagnosisState


def route_after_guard(state: DiagnosisState) -> str:
    """End the run if the upload was not plant material."""
    return "reject" if state.rejected else "continue"


def route_after_quality(state: DiagnosisState) -> str:
    """End the run if the photos cannot support a diagnosis, then decide whether the
    species still has to be identified.

    A re-check normally skips identification — the species is already on record, and
    ``start_recheck`` puts it in state. But a plant whose first diagnosis never managed
    to identify it has no species on record, so ``start_recheck`` leaves ``species``
    unset and the re-check goes through ``identify_plant`` after all; skipping it
    unconditionally meant such a plant could never acquire a species, however many
    re-checks it went through. Either way the run rejoins the re-check path at
    ``route_after_symptoms``, which keys off ``plant_id``.
    """
    if state.quality is not None and not state.quality.usable:
        return "retake"
    if state.plant_id is not None and state.species is not None:
        return "recheck"
    return "continue"


def route_after_symptoms(state: DiagnosisState) -> str:
    """A known plant compares progress against its prior diagnosis instead of
    pausing for clarifying questions — roadmap-step completion already answers
    what a re-check would otherwise have to ask."""
    return "recheck" if state.plant_id is not None else "continue"


def route_after_verdict(state: DiagnosisState) -> str:
    """improving/static revise the existing plan; worsening/new_problem rejoin the
    full diagnosis chain."""
    if state.verdict is not None and state.verdict.verdict in ("improving", "static"):
        return "revise"
    return "escalate"


def build_diagnosis_graph(deps: Deps, checkpointer: BaseCheckpointSaver):
    """Build and compile the diagnosis pipeline.

    Args:
        deps: Everything the nodes need from the outside world.
        checkpointer: State persistence. Required — the graph interrupts, and without
            a checkpointer there is nothing to resume from.
    """
    graph = StateGraph(DiagnosisState)

    graph.add_node("guard_input", make_guard_input(deps))
    graph.add_node("quality_check", make_quality_check(deps))
    graph.add_node("identify_plant", make_identify_plant(deps))
    graph.add_node("assess_symptoms", make_assess_symptoms(deps))
    graph.add_node("select_questions", make_select_questions(deps))
    graph.add_node("gather_context", make_gather_context(deps))
    graph.add_node("enrich", make_enrich(deps))
    graph.add_node("diagnose", make_diagnose(deps))
    graph.add_node("check_contagion", make_check_contagion(deps))
    graph.add_node("build_roadmap", make_build_roadmap(deps))
    graph.add_node("persist", make_persist(deps))
    graph.add_node("compare_progress", make_compare_progress(deps))
    graph.add_node("revise_roadmap", make_revise_roadmap(deps))

    graph.add_edge(START, "guard_input")
    graph.add_conditional_edges(
        "guard_input", route_after_guard, {"reject": END, "continue": "quality_check"}
    )
    graph.add_conditional_edges(
        "quality_check",
        route_after_quality,
        {"retake": END, "continue": "identify_plant", "recheck": "assess_symptoms"},
    )
    graph.add_edge("identify_plant", "assess_symptoms")
    graph.add_conditional_edges(
        "assess_symptoms",
        route_after_symptoms,
        {"continue": "select_questions", "recheck": "compare_progress"},
    )
    graph.add_conditional_edges(
        "compare_progress",
        route_after_verdict,
        {"revise": "revise_roadmap", "escalate": "enrich"},
    )
    graph.add_edge("revise_roadmap", "persist")
    graph.add_edge("select_questions", "gather_context")
    graph.add_edge("gather_context", "enrich")
    graph.add_edge("enrich", "diagnose")
    graph.add_edge("diagnose", "check_contagion")
    graph.add_edge("check_contagion", "build_roadmap")
    graph.add_edge("build_roadmap", "persist")
    graph.add_edge("persist", END)

    return graph.compile(checkpointer=checkpointer)
