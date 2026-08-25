"""Tests for the hypothesise node.

Its job is to name disorders worth reading about, from a supplied list of ids, so that
``enrich`` can fetch documents similarity search ranks too low to return — measured at
16th, 17th and 21st of 43 for three nutrient cases.
"""

import pytest

from agent.nodes.hypothesise import make_hypothesise
from agent.schemas import Hypotheses, Severity, Symptom, SymptomPosition, SymptomSet
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _state(images, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Kitchen basil",
        "location_kind": "indoor",
        "symptoms": SymptomSet(
            symptoms=[
                Symptom(
                    description="pale lower leaves",
                    position=SymptomPosition.LOWER_LEAVES,
                    severity=Severity.MONITOR,
                )
            ],
            soil_condition="evenly moist",
            overall_vigor="declining",
        ),
        "answers": {"fertiliser": "cannot remember the last time it was fed"},
    }
    return DiagnosisState(**{**base, **overrides})


def test_named_disorders_land_on_state(make_deps, sample_images):
    chat = ScriptedStructuredModel(
        [Hypotheses(doc_ids=["nitrogen-deficiency", "overwatering"], reasoning="pale old leaves")]
    )
    node = make_hypothesise(make_deps(chat_model=chat))

    result = node(_state(sample_images))

    assert result["hypotheses"] == ["nitrogen-deficiency", "overwatering"]


def test_the_prompt_offers_the_corpus_ids(make_deps, sample_images, chroma_retriever):
    """The model must pick from real ids or the lookup finds nothing, so the list of
    what exists has to be in the prompt."""
    chat = ScriptedStructuredModel([Hypotheses(doc_ids=["root-rot"], reasoning="x")])
    deps = make_deps(chat_model=chat, retriever=chroma_retriever)

    make_hypothesise(deps)(_state(sample_images))

    prompt = "\n".join(str(m.content) for m in chat.prompts[0])
    for doc_id in chroma_retriever.known_doc_ids():
        assert doc_id in prompt


def test_the_care_answers_are_offered_too(owner, make_deps, sample_images):
    """How often a plant is fed is often what separates two disorders that look
    identical in a photograph, and it is the owner's answers that carry it."""
    chat = ScriptedStructuredModel([Hypotheses(doc_ids=["root-rot"], reasoning="x")])

    make_hypothesise(make_deps(chat_model=chat))(_state(sample_images))

    prompt = "\n".join(str(m.content) for m in chat.prompts[0])
    assert "cannot remember the last time it was fed" in prompt


def test_invented_ids_are_dropped(make_deps, sample_images, caplog):
    """A model naming a disorder the corpus does not hold would retrieve nothing;
    dropping it here keeps that visible in the log rather than silently absorbed."""
    chat = ScriptedStructuredModel(
        [Hypotheses(doc_ids=["root-rot", "sudden-plant-sadness"], reasoning="x")]
    )

    result = make_hypothesise(make_deps(chat_model=chat))(_state(sample_images))

    assert result["hypotheses"] == ["root-rot"]
    assert "sudden-plant-sadness" in caplog.text


def test_a_model_failure_is_not_fatal(make_deps, sample_images):
    """Retrieval still runs on similarity alone, which is what the pipeline did before
    this node existed. Losing precision is acceptable; losing the diagnosis is not."""
    node = make_hypothesise(make_deps(chat_model=FailingChatModel(RuntimeError("judge down"))))

    result = node(_state(sample_images))

    assert "hypotheses" not in result
    assert any("hypothesise" in error for error in result["errors"])


def test_nothing_is_hypothesised_without_symptoms(make_deps, sample_images):
    """No symptoms means the vision step failed; there is nothing to reason from, and
    inventing candidates from a bare species name would be guesswork."""
    chat = ScriptedStructuredModel([])

    result = make_hypothesise(make_deps(chat_model=chat))(_state(sample_images, symptoms=None))

    assert result == {}
    assert chat.call_count == 0


def test_the_step_is_recorded_as_a_tool(make_deps, sample_images):
    """The UI and the trace report what the agent chose to do."""
    chat = ScriptedStructuredModel([Hypotheses(doc_ids=["root-rot"], reasoning="x")])

    result = make_hypothesise(make_deps(chat_model=chat))(_state(sample_images))

    assert "hypothesise" in result["tools_used"]


def test_at_most_eight_disorders_are_accepted():
    """A shortlist for reading, not the whole library: an unbounded list would put the
    entire corpus in the prompt and defeat the point of shortlisting."""
    with pytest.raises(ValueError):
        Hypotheses(doc_ids=[f"disorder-{n}" for n in range(9)])
