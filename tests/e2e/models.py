"""Scripted models for the browser tests.

The rule that no test makes a model call holds in a browser exactly as it holds in a unit
test, and the browser tests drive the whole graph — so every tier is scripted here, not just
the two `eval/scripted.py` covers.

**Dispatch is by requested schema, never by call order.** The graph branches: a re-check of
an unidentified plant calls ``identify_plant`` and a fresh diagnosis may not, and the
retrieval tier asks for ``Hypotheses`` only when the corpus is reachable. A positional queue
desynchronises on the first branch it meets and returns a ``SymptomSet`` where a
``SpeciesGuess`` was asked for, which surfaces as a validation error three nodes later. The
same reasoning is written out at greater length in `eval/scripted.py`.

The answers are fixed and deliberately dull. What a browser test proves is that a run
travels from an upload through an interrupt to a rendered differential — not what the model
said. A varying answer would only make a flake harder to read.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, PrivateAttr

from agent.schemas import (
    Candidate,
    Differential,
    Hypotheses,
    ImageOrgan,
    ImageQuality,
    IPMTier,
    PlantCheck,
    ProgressVerdict,
    Question,
    QuestionSet,
    Roadmap,
    RoadmapStep,
    Severity,
    SpeciesCandidate,
    SpeciesGuess,
    SpeciesMethod,
    Symptom,
    SymptomPosition,
    SymptomSet,
    VisionIdentification,
)

# The two questions the wizard pauses on. `drainage` is the mandatory one the graph adds
# itself; the second exists so a browser test can prove more than one field renders.
QUESTIONS = QuestionSet(
    questions=[
        Question(
            key="watering",
            text="How often do you water it?",
            kind="text",
            options=[],
        ),
        Question(
            key="light",
            text="How much light does it get?",
            kind="choice",
            options=["Bright, indirect", "Direct sun", "Low light"],
        ),
    ]
)

DIFFERENTIAL = Differential(
    is_healthy=False,
    reasoning=(
        "The lower leaves are yellowing from the tips inward while the soil stays wet, "
        "which points at the roots rather than at the light."
    ),
    candidates=[
        Candidate(
            disorder_id="overwatering",
            name="Overwatering",
            probability=0.62,
            supporting_evidence=["The soil surface is wet", "The oldest leaves went first"],
            contradicting_evidence=["No smell from the pot"],
            distinguishing_test="Lift the pot: a waterlogged one is markedly heavier.",
            severity=Severity.ACT_THIS_WEEK,
            transmissible=False,
        ),
        Candidate(
            disorder_id="nitrogen-deficiency",
            name="Nitrogen deficiency",
            probability=0.24,
            supporting_evidence=["Uniform yellowing of the older leaves"],
            contradicting_evidence=["It was potted recently in fresh compost"],
            distinguishing_test="Feed once and look for new growth greening within a fortnight.",
            severity=Severity.MONITOR,
            transmissible=False,
        ),
    ],
)

ROADMAP = Roadmap(
    steps=[
        RoadmapStep(
            ordinal=1,
            action="Stop watering until the top third of the compost is dry",
            rationale="Roots sitting in water cannot take up oxygen",
            success_signal="No new leaves yellow over the next week",
            tier=IPMTier.CULTURAL,
            day_offset=0,
        ),
        RoadmapStep(
            ordinal=2,
            action="Move it somewhere brighter so the pot dries between waterings",
            rationale="A pot that dries out is a pot that cannot stay waterlogged",
            success_signal="The compost is dry to a finger's depth within a week of watering",
            tier=IPMTier.CULTURAL,
            day_offset=7,
        ),
    ]
)


def _for(schema: Any) -> BaseModel:
    """The canned object a node asking for ``schema`` should receive."""
    if schema is PlantCheck:
        return PlantCheck(is_plant=True, what_it_is="a basil plant in a terracotta pot")
    if schema is ImageQuality:
        return ImageQuality(usable=True, problem=None, guidance=None)
    if schema is SpeciesGuess:
        return SpeciesGuess(
            common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.88
        )
    if schema is VisionIdentification:
        # What `identify_plant` actually asks for: the species and each photograph's organ,
        # in one response. The organ then goes to the identification service, which a
        # browser run never reaches — `Deps.identify_species` is bound to a scripted
        # second opinion in `server.py`, not to the real adapter.
        return VisionIdentification(
            common_name="Basil",
            scientific_name="Ocimum basilicum",
            confidence=0.88,
            organs=[ImageOrgan.LEAF],
        )
    if schema is SymptomSet:
        return SymptomSet(
            symptoms=[
                Symptom(
                    description="Yellowing of the lower leaves, from the tip inward",
                    position=SymptomPosition.LOWER_LEAVES,
                    severity=Severity.ACT_THIS_WEEK,
                )
            ],
            soil_condition="wet to the touch",
            overall_vigor="declining",
        )
    if schema is Hypotheses:
        return Hypotheses(doc_ids=["overwatering", "nitrogen-deficiency"], reasoning="scripted")
    if schema is QuestionSet:
        return QUESTIONS
    if schema is Differential:
        return DIFFERENTIAL
    if schema is Roadmap:
        return ROADMAP
    if schema is ProgressVerdict:
        return ProgressVerdict(verdict="improving", reasoning="Fewer leaves are yellow.")

    # Loudly, and naming the schema. A browser test failing three nodes downstream with a
    # validation error is the worst way to find out a node was added.
    raise AssertionError(
        f"no scripted response for {getattr(schema, '__name__', schema)!r}. "
        "A node now asks for a schema the browser tests do not script: add it here."
    )


# What a scripted chat reply consults, and what it says afterwards. One lookup rather than
# none, because the thing worth proving in a browser is that the lookup is *announced* —
# which is only observable when there is one.
LOOKUP = "search_plant_knowledge"
REPLY = (
    "Basil wilts like this when the compost stays wet. Let the top third dry out "
    "before you water it again, and it should pick up within a few days."
)


class ScriptedGraphModel(BaseChatModel):
    """Answers every structured request the graph makes, and runs one chat turn.

    Both, in one class, because both arrive through ``Deps.chat_model`` — the reasoning
    tier is the diagnosis graph's model and the chat agent's model, and a browser session
    uses each in turn.

    The chat half decides what to do from the transcript rather than from a counter: a tool
    call while no tool has answered yet, the reply once one has. A counter would be wrong
    the moment the agent retried, and it would be wrong silently.
    """

    # Whether ``bind_tools`` has been called on this instance. A private attribute rather
    # than a field: it is an implementation detail of the fake, not part of its shape.
    _bound_tools: bool = PrivateAttr(default=False)

    @property
    def _llm_type(self) -> str:
        return "scripted-graph"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        if self._bound_tools and not any(isinstance(m, ToolMessage) for m in messages):
            call = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": LOOKUP,
                        "args": {"query": "basil lower leaves yellowing wet compost"},
                        "id": "scripted-lookup",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=call)])

        content = REPLY if self._bound_tools else "scripted"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        bound = ScriptedGraphModel()
        bound._bound_tools = True
        return bound

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        return RunnableLambda(lambda _messages, _schema=schema: _for(_schema))


# What the scripted identification service answers. Deliberately *disagrees* with the vision
# model above, which says "Basil": two methods naming different plants is the case the choice
# screen exists for, and the one a browser test should be walking through. Agreement is the
# easy case and is covered by unit tests.
SECOND_OPINION = [
    SpeciesCandidate(
        common_name="Thai basil",
        scientific_name="Ocimum africanum",
        confidence=0.71,
        method=SpeciesMethod.PLANTNET,
    ),
    SpeciesCandidate(
        common_name="Holy basil",
        scientific_name="Ocimum tenuiflorum",
        confidence=0.19,
        method=SpeciesMethod.PLANTNET,
    ),
]


def scripted_second_opinion(_photographs) -> list[SpeciesCandidate]:
    """Stands in for the identification service in a browser run.

    Bound in place of the real adapter rather than relying on an absent key, because an
    absent key means no choice is ever offered — and the choice is the thing worth driving
    a browser for.
    """
    return list(SECOND_OPINION)
