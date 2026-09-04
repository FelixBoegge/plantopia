"""Tests for the intake nodes."""

from agent.nodes.intake import make_guard_input, make_quality_check, rejection_message
from agent.schemas import ImageQuality, PlantCheck
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _state(images) -> DiagnosisState:
    return DiagnosisState(images=images, plant_name="Basil", location_kind="indoor")


def test_the_rejection_reads_as_one_sentence():
    """Seen live: "This looks like A screenshot of a web form…., not a plant."

    The model writes a standalone sentence — capitalised, full-stopped — and it is
    interpolated mid-sentence. Both ends need trimming, and the message must not end
    up with two full stops.
    """
    message = rejection_message("A screenshot of a web form.", app_title="Plantopia")

    assert message.startswith("This looks like a screenshot of a web form, not a plant.")
    assert "…." not in message
    assert "A screenshot" not in message


def test_the_rejection_keeps_an_acronym_capitalised():
    """ "NASA logo" is not ordinary prose — its capitals stay."""
    message = rejection_message("NASA logo.", app_title="Plantopia")

    assert message.startswith("This looks like NASA logo, not a plant.")


class TestGuardInput:
    def test_passes_a_plant_image(self, make_deps, sample_images):
        deps = make_deps(
            gate_model=ScriptedStructuredModel(
                [PlantCheck(is_plant=True, what_it_is="a potted basil plant")]
            )
        )
        result = make_guard_input(deps)(_state(sample_images))
        assert result["rejected"] is False

    def test_rejects_a_non_plant_image(self, make_deps, sample_images):
        deps = make_deps(
            gate_model=ScriptedStructuredModel(
                [PlantCheck(is_plant=False, what_it_is="a photograph of a person")]
            )
        )
        result = make_guard_input(deps)(_state(sample_images))
        assert result["rejected"] is True
        assert result["rejection_reason"]

    def test_rejection_reason_mentions_what_was_seen(self, make_deps, sample_images):
        deps = make_deps(
            gate_model=ScriptedStructuredModel(
                [PlantCheck(is_plant=False, what_it_is="a photograph of a person")]
            )
        )
        result = make_guard_input(deps)(_state(sample_images))
        assert "person" in result["rejection_reason"]

    def test_model_failure_rejects_rather_than_proceeding(self, make_deps, sample_images):
        deps = make_deps(gate_model=FailingChatModel(RuntimeError("api down")))
        result = make_guard_input(deps)(_state(sample_images))
        assert result["rejected"] is True
        assert result["errors"]

    def test_the_model_receives_every_image(self, make_deps, sample_images):
        model = ScriptedStructuredModel([PlantCheck(is_plant=True, what_it_is="basil")])
        deps = make_deps(gate_model=model)
        make_guard_input(deps)(_state(sample_images))
        prompt = model.prompts[0]
        image_blocks = [b for b in prompt[-1].content if b["type"] == "image_url"]
        assert len(image_blocks) == len(sample_images)

    def test_the_gate_tier_is_used_not_the_vision_tier(self, make_deps, sample_images):
        """The gate runs on every diagnosis; it must not burn the expensive model."""
        gate = ScriptedStructuredModel([PlantCheck(is_plant=True, what_it_is="basil")])
        vision = ScriptedStructuredModel([])
        deps = make_deps(gate_model=gate, vision_model=vision)
        make_guard_input(deps)(_state(sample_images))
        assert gate.call_count == 1
        assert vision.call_count == 0


class TestQualityCheck:
    def test_usable_image_passes(self, make_deps, sample_images):
        deps = make_deps(
            gate_model=ScriptedStructuredModel(
                [ImageQuality(usable=True, problem=None, guidance=None)]
            )
        )
        result = make_quality_check(deps)(_state(sample_images))
        assert result["quality"].usable is True

    def test_unusable_image_carries_guidance(self, make_deps, sample_images):
        deps = make_deps(
            gate_model=ScriptedStructuredModel(
                [
                    ImageQuality(
                        usable=False,
                        problem="too blurry to see leaf detail",
                        guidance="Retake in daylight, holding the camera still.",
                    )
                ]
            )
        )
        result = make_quality_check(deps)(_state(sample_images))
        assert result["quality"].usable is False
        assert result["quality"].guidance

    def test_model_failure_degrades_to_usable(self, make_deps, sample_images):
        """A quality check that cannot run must not block a diagnosis."""
        deps = make_deps(gate_model=FailingChatModel(RuntimeError("api down")))
        result = make_quality_check(deps)(_state(sample_images))
        assert result["quality"].usable is True
        assert result["errors"]
