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


def _location(questions):
    """The location question, which is now always among them."""
    found = [q for q in questions if q.key == "location"]
    assert len(found) == 1, f"expected exactly one location question, got {len(found)}"
    return found[0]


class TestWhereThePlantIs:
    """Asked here rather than on the upload form, and prefilled where anything knows.

    Two of these tests replaced ones asserting the opposite — that an indoor plant is not
    asked, and that a plant with a known location is not asked again. Both were true of the
    flow where somebody typed their town before starting a run. Now nobody is asked before
    the run, so the question has to be here for everybody; what changes between cases is
    what is already in the field and whether it may be left empty.
    """

    def test_it_is_asked_of_an_outdoor_plant(self, make_deps, sample_images):
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = select_questions(deps, _state(sample_images, location_kind="outdoor"))

        assert _location(questions).required is True

    def test_it_is_asked_of_an_indoor_plant_too_but_optionally(self, make_deps, sample_images):
        """Weather frequently is the diagnosis outdoors, so its absence costs a real part
        of the answer. Indoors the connection is weak enough that demanding one would be
        demanding it for nothing."""
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = select_questions(deps, _state(sample_images, location_kind="indoor"))

        assert _location(questions).required is False

    def test_a_place_read_from_a_photograph_fills_it_in(self, make_deps, sample_images):
        deps = make_deps(
            chat_model=_model_questions("light_hours"),
            place_name=lambda latitude, longitude: "Berlin",
        )
        state = _state(sample_images, location_kind="outdoor", latitude=52.5, longitude=13.4)

        questions = select_questions(deps, state)

        assert _location(questions).prefill == "Berlin"

    def test_a_plants_own_location_fills_it_in_when_the_photograph_knew_nothing(
        self, make_deps, sample_images
    ):
        """A re-check. The plant already carries where it lives, and asking again with an
        empty field would make somebody retype it."""
        deps = make_deps(chat_model=_model_questions("light_hours"))
        state = _state(sample_images, location_kind="outdoor", location_text="Berlin")

        questions = select_questions(deps, state)

        assert _location(questions).prefill == "Berlin"

    def test_nothing_known_leaves_it_empty(self, make_deps, sample_images):
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = select_questions(deps, _state(sample_images, location_kind="outdoor"))

        assert _location(questions).prefill is None

    def test_no_position_means_no_lookup(self, make_deps, sample_images):
        """Most photographs carry none. A lookup for a position that does not exist would
        be a request to a rate-limited free service for nothing."""
        asked = []
        deps = make_deps(
            chat_model=_model_questions("light_hours"),
            place_name=lambda latitude, longitude: asked.append((latitude, longitude)),
        )

        select_questions(deps, _state(sample_images, location_kind="outdoor"))

        assert asked == []

    def test_a_failing_lookup_leaves_the_field_empty(self, make_deps, sample_images):
        """Somebody then types their town, as they did before any of this existed. A place
        name is never worth a failed run."""

        def _explodes(latitude, longitude):
            raise RuntimeError("the service is down")

        deps = make_deps(chat_model=_model_questions("light_hours"), place_name=_explodes)
        state = _state(sample_images, location_kind="outdoor", latitude=52.5, longitude=13.4)

        questions = select_questions(deps, state)

        assert _location(questions).prefill is None
        assert _location(questions).required is True


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


class TestWhenThePhotographWasTaken:
    """Offered for correction, because a forwarded photograph carries somebody else's date.

    That date decides which three weeks of weather the diagnosis is read against, so a wrong
    one is not cosmetic — and it cannot be told from a right one automatically.
    """

    def test_it_is_asked_when_a_photograph_declared_one(self, make_deps, sample_images):
        from datetime import UTC, datetime

        deps = make_deps(chat_model=_model_questions("light_hours"))
        state = _state(sample_images, captured_at=datetime(2026, 8, 10, 10, 50, tzinfo=UTC))

        questions = {q.key: q for q in select_questions(deps, state)}

        assert questions["captured_at"].prefill == "2026-08-10"
        assert questions["captured_at"].kind == "date"

    def test_it_is_not_asked_when_no_photograph_declared_one(self, make_deps, sample_images):
        """The upload date is the honest answer then, and asking would add a control that
        earns nothing — nobody knows a photograph's date better than the photograph, except
        when the photograph is somebody else's."""
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = {q.key for q in select_questions(deps, _state(sample_images))}

        assert "captured_at" not in questions

    def test_it_is_never_required(self, make_deps, sample_images):
        from datetime import UTC, datetime

        deps = make_deps(chat_model=_model_questions("light_hours"))
        state = _state(sample_images, captured_at=datetime(2026, 8, 10, tzinfo=UTC))

        questions = {q.key: q for q in select_questions(deps, state)}

        assert questions["captured_at"].required is False


class TestCorrectingTheCaptureDate:
    def test_a_corrected_date_replaces_what_the_photograph_said(self):
        from datetime import UTC, datetime

        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"captured_at": "2026-08-05"}, "species": None})

        assert result["captured_at"] == datetime(2026, 8, 5, tzinfo=UTC)

    def test_clearing_it_falls_back_to_the_upload_date(self):
        """`None` is where every photograph that declared nothing already ends up."""
        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"captured_at": ""}, "species": None})

        assert result["captured_at"] is None

    def test_a_question_that_was_never_asked_changes_nothing(self):
        """Absent is different from empty: the run keeps what the photograph said."""
        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"watering": "twice"}, "species": None})

        assert "captured_at" not in result

    def test_an_unusable_date_is_ignored_rather_than_believed(self):
        """Nothing should send this. Believed, it would ask for weather from a time that
        does not exist; raised, it would fail a run in the half after the expensive part."""
        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"captured_at": "the day before yesterday"}, "species": None})

        assert "captured_at" not in result
