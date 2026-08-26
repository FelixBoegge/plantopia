"""Control-flow tests over the assembled diagnosis graph.

These cover the agentic behaviour: the mandatory interrupt, the rejection paths, and
resumption from a checkpoint. A node can be individually correct while the graph
routes wrongly, and only these tests would catch that.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import func, select

from agent.diagnosis_graph import build_diagnosis_graph
from agent.schemas import ImageQuality, PlantCheck
from agent.state import DiagnosisState
from data.models import Diagnosis, Plant
from data.models import RoadmapStep as RoadmapStepRow
from tests.fakes.chat_models import ScriptedStructuredModel


@pytest.fixture
def config():
    return {"configurable": {"thread_id": "test-thread"}}


def _initial(images, **overrides) -> DiagnosisState:
    base = {"images": images, "plant_name": "Kitchen basil", "location_kind": "indoor"}
    return DiagnosisState(**{**base, **overrides})


class TestInterrupt:
    def test_the_graph_halts_at_gather_context(
        self, make_deps, sample_images, pipeline_models, config
    ):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        result = graph.invoke(_initial(sample_images), config)
        assert "__interrupt__" in result

    def test_the_interrupt_carries_the_questions(
        self, make_deps, sample_images, pipeline_models, config
    ):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        result = graph.invoke(_initial(sample_images), config)
        payload = result["__interrupt__"][0].value
        keys = {q["key"] for q in payload["questions"]}
        assert "watering" in keys
        assert "drainage" in keys

    def test_diagnosis_is_not_reached_before_the_resume(
        self, make_deps, sample_images, pipeline_models, config, db
    ):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        graph.invoke(_initial(sample_images), config)

        state = graph.get_state(config)
        assert state.values.get("differential") is None
        assert db.scalar(select(func.count()).select_from(Diagnosis)) == 0

    def test_resuming_completes_the_run(self, make_deps, sample_images, pipeline_models, config):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        graph.invoke(_initial(sample_images), config)

        final = graph.invoke(
            Command(resume={"watering": "every other day", "drainage": "No drainage holes"}),
            config,
        )
        assert final["differential"] is not None
        assert final["differential"].primary.disorder_id == "overwatering"

    def test_the_answers_survive_the_resume(
        self, make_deps, sample_images, pipeline_models, config
    ):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        graph.invoke(_initial(sample_images), config)
        final = graph.invoke(Command(resume={"watering": "every other day"}), config)
        assert final["answers"]["watering"] == "every other day"

    def test_a_completed_run_persists_everything(
        self, make_deps, sample_images, pipeline_models, config, db
    ):
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        graph.invoke(_initial(sample_images), config)
        graph.invoke(Command(resume={"watering": "every other day"}), config)

        assert db.scalar(select(func.count()).select_from(Plant)) == 1
        assert db.scalar(select(func.count()).select_from(Diagnosis)) == 1
        assert db.scalar(select(func.count()).select_from(RoadmapStepRow)) == 1


class TestRejectionPaths:
    def test_a_non_plant_image_ends_the_run_immediately(self, make_deps, sample_images, config, db):
        gate = ScriptedStructuredModel(
            [PlantCheck(is_plant=False, what_it_is="a photograph of a person")]
        )
        graph = build_diagnosis_graph(make_deps(gate_model=gate), MemorySaver())
        result = graph.invoke(_initial(sample_images), config)

        assert result["rejected"] is True
        assert result.get("species") is None
        assert "__interrupt__" not in result

    def test_a_rejected_image_writes_nothing(self, make_deps, sample_images, config, db):
        gate = ScriptedStructuredModel([PlantCheck(is_plant=False, what_it_is="a kitchen worktop")])
        graph = build_diagnosis_graph(make_deps(gate_model=gate), MemorySaver())
        graph.invoke(_initial(sample_images), config)
        assert db.scalar(select(func.count()).select_from(Plant)) == 0

    def test_an_unusable_photo_ends_the_run_with_guidance(self, make_deps, sample_images, config):
        gate = ScriptedStructuredModel(
            [
                PlantCheck(is_plant=True, what_it_is="a plant, very blurry"),
                ImageQuality(
                    usable=False,
                    problem="too blurry",
                    guidance="Retake in daylight, holding the camera still.",
                ),
            ]
        )
        graph = build_diagnosis_graph(make_deps(gate_model=gate), MemorySaver())
        result = graph.invoke(_initial(sample_images), config)

        assert result["quality"].usable is False
        assert result.get("species") is None
        assert "__interrupt__" not in result


class TestOrdering:
    def test_species_is_identified_before_symptoms_are_assessed(
        self, make_deps, sample_images, pipeline_models, config
    ):
        """The scripted vision model would return the wrong object if order changed."""
        gate, vision, chat = pipeline_models
        graph = build_diagnosis_graph(
            make_deps(gate_model=gate, vision_model=vision, chat_model=chat), MemorySaver()
        )
        graph.invoke(_initial(sample_images), config)
        state = graph.get_state(config)
        assert state.values["species"].common_name == "Basil"
        assert state.values["symptoms"] is not None

    def test_an_outdoor_plant_reaches_the_weather_tool(
        self, make_deps, sample_images, pipeline_models, config
    ):
        calls: list[tuple] = []

        def _weather(location, days):
            calls.append((location, days))
            return None

        gate, vision, chat = pipeline_models
        deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat, weather=_weather)
        graph = build_diagnosis_graph(deps, MemorySaver())
        graph.invoke(
            _initial(sample_images, location_kind="outdoor", location_text="Berlin"), config
        )
        graph.invoke(Command(resume={"watering": "weekly"}), config)
        assert calls and calls[0][0] == "Berlin"

    def test_an_indoor_plant_never_reaches_the_weather_tool(
        self, make_deps, sample_images, pipeline_models, config
    ):
        calls: list[tuple] = []

        def _weather(location, days):
            calls.append((location, days))
            return None

        gate, vision, chat = pipeline_models
        deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat, weather=_weather)
        graph = build_diagnosis_graph(deps, MemorySaver())
        graph.invoke(_initial(sample_images, location_kind="indoor"), config)
        graph.invoke(Command(resume={"watering": "weekly"}), config)
        assert calls == []


class TestStudioEntryPoint:
    """The graph as the LangGraph dev server behind Studio builds it.

    Studio's value is that it draws the graph that actually runs, which only holds if
    both are assembled by the same builder. These cover the one difference between the
    two callers — the API server attaches its own persistence, so it asks for a graph
    with no checkpointer fitted — and pin the topology the diagram is drawn from.
    """

    def test_the_graph_compiles_without_a_checkpointer(self, make_deps):
        """``checkpointer=None`` is a supported call, not an accident: the API server
        refuses a graph that arrives with one already attached."""
        graph = build_diagnosis_graph(make_deps(), checkpointer=None)

        assert graph.checkpointer is None

    def test_every_node_and_router_is_reachable_in_the_drawn_graph(self, make_deps):
        """What Studio renders comes from ``get_graph()``. Asserted here so a node
        added to the builder but never wired to an edge — invisible in the app until
        something fails to run — shows up as a test failure instead.
        """
        drawn = build_diagnosis_graph(make_deps(), checkpointer=None).get_graph()

        assert set(drawn.nodes) == {
            "__start__",
            "__end__",
            "guard_input",
            "quality_check",
            "identify_plant",
            "assess_symptoms",
            "select_questions",
            "gather_context",
            "hypothesise",
            "enrich",
            "diagnose",
            "check_contagion",
            "build_roadmap",
            "persist",
            "compare_progress",
            "revise_roadmap",
        }
        # Every node bar START must be someone's target, or it can never run.
        targets = {edge.target for edge in drawn.edges}
        assert set(drawn.nodes) - {"__start__"} <= targets


class TestTheIdentificationAtThePause:
    """Whether the owner is asked which plant it is, driven through the real graph.

    The rule is only ever "how many candidates survived": one means every method, and the
    owner if they said anything, named the same plant, and asking somebody to confirm what
    nobody disputed is an interruption rather than a choice.
    """

    def _graph(self, make_deps, pipeline_models, **overrides):
        gate, vision, chat = pipeline_models
        deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat, **overrides)
        return build_diagnosis_graph(deps, MemorySaver())

    def test_a_disagreement_is_put_to_the_owner(
        self, make_deps, sample_images, pipeline_models, config
    ):
        from agent.schemas import SpeciesCandidate, SpeciesMethod

        graph = self._graph(
            make_deps,
            pipeline_models,
            identify_species=lambda _: [
                SpeciesCandidate(
                    common_name="Mint",
                    scientific_name="Mentha spicata",
                    confidence=0.7,
                    method=SpeciesMethod.PLANTNET,
                )
            ],
        )

        result = graph.invoke(_initial(sample_images), config)

        payload = result["__interrupt__"][0].value
        assert [c["common_name"] for c in payload["identification"]] == ["Basil", "Mint"]
        # And the questions are still there: one pause, both things.
        assert payload["questions"]

    def test_agreement_asks_nothing_about_the_species(
        self, make_deps, sample_images, pipeline_models, config
    ):
        from agent.schemas import SpeciesCandidate, SpeciesMethod

        graph = self._graph(
            make_deps,
            pipeline_models,
            identify_species=lambda _: [
                SpeciesCandidate(
                    common_name="Sweet basil",
                    scientific_name="Ocimum basilicum",
                    confidence=0.9,
                    method=SpeciesMethod.PLANTNET,
                )
            ],
        )

        result = graph.invoke(_initial(sample_images), config)

        payload = result["__interrupt__"][0].value
        assert "identification" not in payload
        assert payload["questions"]

    def test_one_method_alone_asks_nothing_about_the_species(
        self, make_deps, sample_images, pipeline_models, config
    ):
        """The shape of every run on a deployment with no key for the second service."""
        graph = self._graph(make_deps, pipeline_models, identify_species=lambda _: [])

        result = graph.invoke(_initial(sample_images), config)

        assert "identification" not in result["__interrupt__"][0].value

    def test_the_question_shape_is_untouched_by_any_of_this(
        self, make_deps, sample_images, pipeline_models, config
    ):
        """The candidates are their own block precisely so this stays true — a chooser
        squeezed into `Question` would have meant a question carrying data no question has,
        and `tests/api/test_question_shape_agrees.py` would have stopped meaning anything.
        """
        from agent.schemas import Question

        graph = self._graph(make_deps, pipeline_models, identify_species=lambda _: [])

        result = graph.invoke(_initial(sample_images), config)

        for asked in result["__interrupt__"][0].value["questions"]:
            assert set(asked) == set(Question.model_fields)

    def test_resuming_with_a_choice_proceeds_on_it(
        self, make_deps, sample_images, pipeline_models, config
    ):
        from langgraph.types import Command

        from agent.schemas import SpeciesCandidate, SpeciesMethod

        graph = self._graph(
            make_deps,
            pipeline_models,
            identify_species=lambda _: [
                SpeciesCandidate(
                    common_name="Mint",
                    scientific_name="Mentha spicata",
                    confidence=0.7,
                    method=SpeciesMethod.PLANTNET,
                )
            ],
        )
        graph.invoke(_initial(sample_images), config)

        result = graph.invoke(
            Command(
                resume={
                    "answers": {"watering": "twice a week"},
                    "species": {
                        "common_name": "Mint",
                        "scientific_name": "Mentha spicata",
                        "confidence": 0.7,
                    },
                }
            ),
            config,
        )

        assert result["species"].common_name == "Mint"
        assert result["species_confirmed"] is True

    def test_resuming_without_a_choice_keeps_the_leader(
        self, make_deps, sample_images, pipeline_models, config
    ):
        from langgraph.types import Command

        from agent.schemas import SpeciesCandidate, SpeciesMethod

        graph = self._graph(
            make_deps,
            pipeline_models,
            identify_species=lambda _: [
                SpeciesCandidate(
                    common_name="Mint",
                    scientific_name="Mentha spicata",
                    confidence=0.99,
                    method=SpeciesMethod.PLANTNET,
                )
            ],
        )
        graph.invoke(_initial(sample_images), config)

        result = graph.invoke(
            Command(resume={"answers": {"watering": "twice a week"}, "species": None}),
            config,
        )

        assert result["species"].common_name == "Basil"
        assert result["species_confirmed"] is False
