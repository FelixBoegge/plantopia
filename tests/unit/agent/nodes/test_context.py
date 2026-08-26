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
from tests.secrets import TEST_JWT_SECRET


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
        settings=Settings(
            openrouter_api_key="sk-test",
            jwt_secret=TEST_JWT_SECRET,
            max_clarifying_questions=4,
            _env_file=None,
        ),
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
        settings=Settings(
            openrouter_api_key="sk-test",
            jwt_secret=TEST_JWT_SECRET,
            max_clarifying_questions=2,
            _env_file=None,
        ),
    )
    keys = {q.key for q in select_questions(deps, _state(sample_images))}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300


def test_a_cap_below_the_mandatory_count_cannot_evict_them(make_deps, sample_images):
    deps = make_deps(
        chat_model=_model_questions("a", "b"),
        settings=Settings(
            openrouter_api_key="sk-test",
            jwt_secret=TEST_JWT_SECRET,
            max_clarifying_questions=1,
            _env_file=None,
        ),
    )
    keys = {q.key for q in select_questions(deps, _state(sample_images))}
    assert ALWAYS_ASK_KEYS <= keys  # noqa: SIM300


class TestResumingWithAChoice:
    """What a resume payload means, at the node that reads it.

    `_resumed` is a pure function over what the client sent, so it is tested directly
    rather than by driving a graph twice — the graph-level version of this is
    `tests/graph/test_diagnosis_graph.py`, and it proves the resume happens at all rather
    than what each field means.
    """

    def test_the_old_shape_is_still_answers(self):
        """A run paused before this deployment resumes after it. The mapping *is* the
        answers, and reading only the new shape would silently drop every one of them."""
        from agent.nodes.context import _resumed

        assert _resumed({"watering": "twice a week"}) == {"answers": {"watering": "twice a week"}}

    def test_answers_without_a_species(self):
        from agent.nodes.context import _resumed

        assert _resumed({"answers": {"watering": "twice"}, "species": None}) == {
            "answers": {"watering": "twice"}
        }

    def test_a_chosen_species_is_written_to_state(self):
        from agent.nodes.context import _resumed

        result = _resumed(
            {
                "answers": {"watering": "twice"},
                "species": {
                    "common_name": "Thai basil",
                    "scientific_name": "Ocimum africanum",
                    "confidence": 0.71,
                },
            }
        )

        assert result["species"].common_name == "Thai basil"
        assert result["species"].scientific_name == "Ocimum africanum"

    def test_choosing_records_that_a_person_chose(self):
        """Distinct from the leading candidate happening to be right, which is what makes a
        wrong diagnosis attributable afterwards."""
        from agent.nodes.context import _resumed

        result = _resumed(
            {"answers": {}, "species": {"common_name": "Thai basil", "confidence": 0.71}}
        )

        assert result["species_confirmed"] is True

    def test_not_choosing_records_nothing(self):
        from agent.nodes.context import _resumed

        assert "species_confirmed" not in _resumed({"answers": {}, "species": None})

    def test_a_resume_that_is_not_a_mapping_is_survived(self):
        """Nothing should send this. A node that raised on it would fail a run somebody
        paid for, in the half after the expensive part."""
        from agent.nodes.context import _resumed

        assert _resumed(None) == {"answers": {}}
        assert _resumed("answers") == {"answers": {}}
