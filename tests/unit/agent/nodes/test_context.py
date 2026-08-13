"""Tests for clarifying-question selection."""

from agent.nodes.context import ALWAYS_ASK_KEYS, select_questions
from agent.schemas import (
    Question,
    QuestionSet,
    Severity,
    SpeciesGuess,
    Symptom,
    SymptomPosition,
    SymptomSet,
)
from agent.state import DiagnosisState
from core.config import Settings
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _symptoms() -> SymptomSet:
    return SymptomSet(
        symptoms=[
            Symptom(
                description="Yellowing",
                position=SymptomPosition.LOWER_LEAVES,
                severity=Severity.ACT_THIS_WEEK,
            )
        ],
        soil_condition="wet",
        overall_vigor="declining",
    )


def _state(images, **overrides) -> DiagnosisState:
    base = {
        "images": images,
        "plant_name": "Basil",
        "location_kind": "indoor",
        "symptoms": _symptoms(),
        "species": SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9),
    }
    return DiagnosisState(**{**base, **overrides})


def _model_questions(*keys: str) -> ScriptedStructuredModel:
    return ScriptedStructuredModel(
        [
            QuestionSet(
                questions=[Question(key=k, text=f"Tell me about {k}?", kind="text") for k in keys]
            )
        ]
    )


def test_always_asked_questions_are_present(make_deps, sample_images):
    deps = make_deps(chat_model=_model_questions("light_hours"))
    questions = select_questions(deps, _state(sample_images))
    keys = {q.key for q in questions}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300


def test_model_questions_are_included(make_deps, sample_images):
    deps = make_deps(chat_model=_model_questions("light_hours"))
    questions = select_questions(deps, _state(sample_images))
    assert "light_hours" in {q.key for q in questions}


def test_count_is_capped_at_the_configured_maximum(make_deps, sample_images):
    deps = make_deps(
        chat_model=_model_questions("a", "b", "c", "d", "e", "f"),
        settings=Settings(openrouter_api_key="sk-test", max_clarifying_questions=4, _env_file=None),
    )
    assert len(select_questions(deps, _state(sample_images))) == 4


def test_at_least_one_question_is_always_returned(make_deps, sample_images):
    deps = make_deps(chat_model=ScriptedStructuredModel([QuestionSet(questions=[])]))
    assert select_questions(deps, _state(sample_images))


def test_duplicate_keys_are_removed(make_deps, sample_images):
    duplicate = next(iter(ALWAYS_ASK_KEYS))
    deps = make_deps(chat_model=_model_questions(duplicate, "light_hours"))
    keys = [q.key for q in select_questions(deps, _state(sample_images))]
    assert len(keys) == len(set(keys))


def test_outdoor_plants_are_asked_for_a_location(make_deps, sample_images):
    deps = make_deps(chat_model=_model_questions("light_hours"))
    questions = select_questions(deps, _state(sample_images, location_kind="outdoor"))
    assert "location" in {q.key for q in questions}


def test_indoor_plants_are_not_asked_for_a_location(make_deps, sample_images):
    deps = make_deps(chat_model=_model_questions("light_hours"))
    questions = select_questions(deps, _state(sample_images, location_kind="indoor"))
    assert "location" not in {q.key for q in questions}


def test_outdoor_plant_with_a_known_location_is_not_asked_again(make_deps, sample_images):
    deps = make_deps(chat_model=_model_questions("light_hours"))
    state = _state(sample_images, location_kind="outdoor", location_text="Berlin")
    assert "location" not in {q.key for q in select_questions(deps, state)}


def test_model_failure_still_yields_the_always_asked_questions(make_deps, sample_images):
    deps = make_deps(chat_model=FailingChatModel(RuntimeError("api down")))
    keys = {q.key for q in select_questions(deps, _state(sample_images))}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300


def test_always_asked_questions_survive_the_cap(make_deps, sample_images):
    """The cap must never evict a question we consider mandatory."""
    deps = make_deps(
        chat_model=_model_questions("a", "b", "c", "d", "e"),
        settings=Settings(openrouter_api_key="sk-test", max_clarifying_questions=2, _env_file=None),
    )
    keys = {q.key for q in select_questions(deps, _state(sample_images))}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300


def test_a_cap_below_the_mandatory_count_cannot_evict_them(make_deps, sample_images):
    deps = make_deps(
        chat_model=_model_questions("a", "b"),
        settings=Settings(openrouter_api_key="sk-test", max_clarifying_questions=1, _env_file=None),
    )
    keys = {q.key for q in select_questions(deps, _state(sample_images))}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300
