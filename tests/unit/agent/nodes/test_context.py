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


def _capped_at(maximum: int) -> Settings:
    return Settings(
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        max_clarifying_questions=maximum,
        _env_file=None,
    )


def test_the_models_questions_are_capped_at_the_configured_maximum(make_deps, sample_images):
    """The cap governs what the agent thinks of, not the four fixed fields.

    It used to govern the whole list, which was the same thing when two of the four did not
    exist. A configured maximum of four now leaves the model nothing — and the model's
    questions are the ones that discriminate in the specific case rather than in general.
    """
    deps = make_deps(
        chat_model=_model_questions("a", "b", "c", "d", "e", "f"),
        settings=_capped_at(2),
    )

    keys = [q.key for q in select_questions(deps, _state(sample_images))]

    assert keys[:4] == ["watering", "drainage", "location", "captured_at"]
    assert keys[4:] == ["a", "b"]


def test_the_fixed_fields_survive_a_cap_of_one(make_deps, sample_images):
    """Somebody who wants to be asked as little as possible still has to be asked where the
    plant is and when the photograph was taken — without those there is no weather at all,
    which is a different thing from a shorter form."""
    deps = make_deps(chat_model=_model_questions("a", "b"), settings=_capped_at(1))

    keys = [q.key for q in select_questions(deps, _state(sample_images))]

    assert keys == ["watering", "drainage", "location", "captured_at", "a"]


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


def test_always_asked_questions_survive_the_cap(make_deps, sample_images):  # noqa: D103
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
    """Always asked, and always carrying a date.

    Every diagnosis is read against a stretch of weather and this decides which stretch, so
    the field is never empty: it holds what the photograph declared, or today, and somebody
    who knows better changes it.
    """

    def test_it_is_prefilled_from_the_photograph(self, make_deps, sample_images):
        from datetime import UTC, datetime

        deps = make_deps(chat_model=_model_questions("light_hours"))
        state = _state(sample_images, captured_at=datetime(2026, 8, 10, 10, 50, tzinfo=UTC))

        questions = {q.key: q for q in select_questions(deps, state)}

        assert questions["captured_at"].prefill == "2026-08-10"
        assert questions["captured_at"].kind == "date"

    def test_it_is_prefilled_with_today_when_the_photograph_said_nothing(
        self, make_deps, sample_images, now
    ):
        """The common case — messaging apps strip metadata and browser capture rarely has
        any. A guess somebody can see is a guess somebody can fix; the alternative is a
        silent assumption quietly deciding part of the answer."""
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = {q.key: q for q in select_questions(deps, _state(sample_images))}

        assert questions["captured_at"].prefill == now().date().isoformat()

    def test_it_says_when_the_date_is_only_a_guess(self, make_deps, sample_images):
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = {q.key: q for q in select_questions(deps, _state(sample_images))}

        assert "did not record" in (questions["captured_at"].prefill_note or "")

    def test_it_says_when_the_date_came_from_the_photograph(self, make_deps, sample_images):
        from datetime import UTC, datetime

        deps = make_deps(chat_model=_model_questions("light_hours"))
        state = _state(sample_images, captured_at=datetime(2026, 8, 10, tzinfo=UTC))

        questions = {q.key: q for q in select_questions(deps, state)}

        assert questions["captured_at"].prefill_note == "Recorded by your camera"

    def test_it_has_to_carry_a_date(self, make_deps, sample_images):
        """An empty date is not a smaller answer than a wrong one. It is no weather at
        all."""
        deps = make_deps(chat_model=_model_questions("light_hours"))

        questions = {q.key: q for q in select_questions(deps, _state(sample_images))}

        assert questions["captured_at"].required is True


class TestCorrectingTheCaptureDate:
    def test_a_corrected_date_replaces_what_the_photograph_said(self):
        from datetime import UTC, datetime

        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"captured_at": "2026-08-05"}, "species": None})

        assert result["captured_at"] == datetime(2026, 8, 5, tzinfo=UTC)

    def test_an_empty_answer_leaves_what_was_there(self):
        """The question is required, so this should not arrive — the form refuses it and so
        does the service. If one does, losing the date would silently widen the window to
        wherever today happens to be, which is worse than the answer somebody failed to
        give."""
        from agent.nodes.context import _resumed

        result = _resumed({"answers": {"captured_at": ""}, "species": None})

        assert "captured_at" not in result

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


class TestWhatTheAgentIsAskedToAskAbout:
    """The subject of the generated questions, pinned.

    A prompt is the easiest thing in a codebase to rewrite by accident: it is prose, it
    reads like documentation, and nothing breaks when its meaning changes. These assert the
    two properties this project depends on rather than the wording.
    """

    @staticmethod
    def _prompt() -> str:
        """The prompt as one line.

        A phrase that happens to straddle a line break is the same instruction to a model
        and a different string to `in`. Normalising here means these tests pin the meaning
        rather than the wrapping — which is what a reformat is allowed to change.
        """
        from agent.prompts.context import SELECT_QUESTIONS

        return " ".join(SELECT_QUESTIONS.lower().split())

    def test_it_asks_about_what_has_already_been_done(self):
        """A plan that opens with "try feeding it" is worse than useless for somebody who
        fed it last week — it costs them a fortnight of watching a plant get worse while
        they wait for a treatment they already applied."""
        prompt = self._prompt()
        assert "repot" in prompt
        assert "fed" in prompt or "feeding" in prompt
        assert "treatment" in prompt or "treated" in prompt

    def test_it_is_told_not_to_ask_what_is_already_asked(self):
        """Four fields are fixed. A model asking for them again would produce two boxes for
        one fact, and the person would reasonably wonder which one counted."""
        prompt = self._prompt()
        assert "watering frequency" in prompt
        assert "drainage" in prompt
        assert "where the plant is" in prompt
        assert "when the photograph was taken" in prompt

    def test_the_fixed_keys_are_the_ones_the_prompt_excludes(self, make_deps, sample_images):
        """The prompt says what not to ask; this says what is asked. Two lists that have to
        agree, in different languages, and nothing else notices when they stop."""
        deps = make_deps(chat_model=_model_questions("light_hours"))

        keys = [q.key for q in select_questions(deps, _state(sample_images))]

        assert keys[:4] == ["watering", "drainage", "location", "captured_at"]

    def test_it_asks_for_three_or_four(self, make_deps, sample_images):
        """Fewer than three rarely covers a plant's recent history — repotted, fed, moved
        and treated are separate facts. More than four is an interrogation."""
        assert "three and four" in self._prompt()

    def test_the_cap_lets_four_through(self, make_deps, sample_images):
        """The prompt asking for four and the cap allowing two would silently discard the
        last two, and the discarding happens after the model has been paid for them."""
        deps = make_deps(chat_model=_model_questions("a", "b", "c", "d"))

        keys = [q.key for q in select_questions(deps, _state(sample_images))]

        assert keys[4:] == ["a", "b", "c", "d"]
