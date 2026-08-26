"""Species identification, by two methods that do not have to agree."""

import pytest

from agent.nodes.identify import make_identify_plant
from agent.schemas import (
    ImageOrgan,
    SpeciesCandidate,
    SpeciesGuess,
    SpeciesMethod,
    VisionIdentification,
)
from agent.state import DiagnosisState
from tests.fakes.chat_models import FailingChatModel, ScriptedStructuredModel


def _state(images, **overrides) -> DiagnosisState:
    return DiagnosisState(images=images, plant_name="My plant", location_kind="indoor", **overrides)


def _seen(
    common_name: str = "Basil",
    scientific_name: str | None = "Ocimum basilicum",
    confidence: float = 0.85,
    organs: list[str] | None = None,
) -> VisionIdentification:
    return VisionIdentification(
        common_name=common_name,
        scientific_name=scientific_name,
        confidence=confidence,
        organs=organs if organs is not None else ["leaf"],
    )


def _candidate(
    common_name: str,
    scientific_name: str | None = None,
    confidence: float = 0.6,
) -> SpeciesCandidate:
    return SpeciesCandidate(
        common_name=common_name,
        scientific_name=scientific_name,
        confidence=confidence,
        method=SpeciesMethod.PLANTNET,
    )


class TestTheVisionIdentification:
    def test_records_the_species_guess(self, make_deps, sample_images):
        deps = make_deps(vision_model=ScriptedStructuredModel([_seen()]))

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["species"] == SpeciesGuess(
            common_name="Basil", scientific_name="Ocimum basilicum", confidence=0.85
        )

    def test_asks_the_model_once_not_twice(self, make_deps, sample_images):
        """The organs and the species come back together. A second call to tag the organs
        would be model spend on every diagnosis, to save a second or two of ninety."""
        model = ScriptedStructuredModel([_seen()])
        deps = make_deps(vision_model=model)

        make_identify_plant(deps)(_state(sample_images))

        assert model.call_count == 1

    def test_failure_yields_an_unknown_zero_confidence_guess(self, make_deps, sample_images):
        deps = make_deps(vision_model=FailingChatModel(RuntimeError("api down")))

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["species"].confidence == 0.0
        assert result["species"].common_name == "Unknown"
        assert result["errors"]

    def test_does_not_ask_the_specialist_when_the_vision_call_failed(
        self, make_deps, sample_images
    ):
        """It takes the organs as input and there are none."""
        asked = []
        deps = make_deps(
            vision_model=FailingChatModel(RuntimeError("api down")),
            identify_species=lambda photographs: asked.append(photographs) or [],
        )

        make_identify_plant(deps)(_state(sample_images))

        assert asked == []

    def test_the_owners_name_for_the_plant_is_never_sent(self, make_deps, sample_images):
        """This test used to assert the opposite, and the reversal is the point.

        A vision model told what the owner thinks tends to agree with the owner. Then
        "both methods and the owner agree" is not corroboration, it is one claim echoed
        back twice — and the entire value of a second opinion is that it was reached
        separately.

        The nickname is the less obvious leak of the two: "Kitchen basil" is not a species
        field, and it contains the answer.
        """
        model = ScriptedStructuredModel([_seen()])
        deps = make_deps(vision_model=model)
        state = _state(sample_images, stated_species="Ocimum basilicum")
        state.plant_name = "my kitchen basil"

        make_identify_plant(deps)(state)

        sent = model.prompts[0][-1].content[0]["text"]
        assert "kitchen" not in sent.casefold()
        assert "basil" not in sent.casefold()
        assert "ocimum" not in sent.casefold()

    def test_nothing_the_owner_said_reaches_the_system_prompt_either(
        self, make_deps, sample_images
    ):
        """The instruction half of the message, checked separately: a hint moved into the
        system prompt would pass the test above and defeat its purpose."""
        model = ScriptedStructuredModel([_seen()])
        deps = make_deps(vision_model=model)
        state = _state(sample_images, stated_species="Ocimum basilicum")
        state.plant_name = "my kitchen basil"

        make_identify_plant(deps)(state)

        system = model.prompts[0][0].content
        assert "kitchen" not in system.casefold()
        assert "ocimum" not in system.casefold()

    def test_an_already_identified_species_is_not_re_identified(self, make_deps, sample_images):
        """The re-check flow reuses this node with the species already known."""
        known = SpeciesGuess(common_name="Basil", scientific_name=None, confidence=0.9)
        model = ScriptedStructuredModel([])
        asked = []
        deps = make_deps(
            vision_model=model,
            identify_species=lambda photographs: asked.append(photographs) or [],
        )

        result = make_identify_plant(deps)(_state(sample_images, species=known))

        assert result == {}
        assert model.call_count == 0
        assert asked == []


class TestTheOrgansItSends:
    def test_sends_the_organ_the_vision_model_reported(self, make_deps, sample_images):
        sent = []
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen(organs=["flower"])]),
            identify_species=lambda photographs: sent.extend(photographs) or [],
        )

        make_identify_plant(deps)(_state(sample_images))

        assert [organ for _, organ in sent] == [ImageOrgan.FLOWER]

    def test_sends_the_photographs_themselves(self, make_deps, sample_images):
        """Bytes, not keys. The specialist has no access to this project's blob store."""
        sent = []
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda photographs: sent.extend(photographs) or [],
        )

        make_identify_plant(deps)(_state(sample_images))

        assert all(isinstance(data, bytes) and data for data, _ in sent)

    def test_an_organ_outside_the_vocabulary_becomes_unknown(self, make_deps, sample_images):
        """The organ is a hint; the species is the answer. Refusing the whole response
        because the model called something a "stem" would throw away a good identification
        over a bad hint."""
        sent = []
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen(organs=["stem"])]),
            identify_species=lambda photographs: sent.extend(photographs) or [],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert [organ for _, organ in sent] == [ImageOrgan.UNKNOWN]
        assert result["species"].common_name == "Basil"

    def test_too_few_organs_leaves_the_rest_unknown(self, make_deps, sample_images):
        """Models return the wrong number of things. Not worth failing over."""
        sent = []
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen(organs=[])]),
            identify_species=lambda photographs: sent.extend(photographs) or [],
        )

        make_identify_plant(deps)(_state(sample_images))

        assert [organ for _, organ in sent] == [ImageOrgan.UNKNOWN]


class TestWhatTheTwoMethodsProduce:
    def test_carries_both_answers_when_they_disagree(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [_candidate("Mint", "Mentha spicata", 0.7)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert [c.common_name for c in result["candidates"]] == ["Basil", "Mint"]
        assert [c.method for c in result["candidates"]] == [
            SpeciesMethod.VISION,
            SpeciesMethod.PLANTNET,
        ]

    def test_collapses_agreement_into_one_candidate_that_says_so(self, make_deps, sample_images):
        """Showing it twice would present the strongest signal available as two things to
        choose between rather than one thing twice confirmed."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [_candidate("Sweet basil", "Ocimum basilicum", 0.91)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert len(result["candidates"]) == 1
        assert result["candidates"][0].method is SpeciesMethod.AGREED
        assert result["candidates"][0].confidence == pytest.approx(0.91)

    def test_agreement_is_decided_on_the_scientific_name(self, make_deps, sample_images):
        """Two different plants share the common name "Mini monstera" in the recorded
        response. A common-name comparison would call them the same plant."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel(
                [_seen("Mini monstera", "Rhaphidophora tetrasperma", 0.6)]
            ),
            identify_species=lambda _: [_candidate("Mini monstera", "Monstera minima", 0.5)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert len(result["candidates"]) == 2
        assert {c.method for c in result["candidates"]} == {
            SpeciesMethod.VISION,
            SpeciesMethod.PLANTNET,
        }

    def test_falls_back_to_the_common_name_when_there_is_no_scientific_one(
        self, make_deps, sample_images
    ):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen("Basil", None)]),
            identify_species=lambda _: [_candidate("basil", None, 0.7)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert len(result["candidates"]) == 1
        assert result["candidates"][0].method is SpeciesMethod.AGREED

    def test_the_species_stays_the_vision_models_until_somebody_chooses(
        self, make_deps, sample_images
    ):
        """Not the highest-confidence candidate: the two methods report confidence on
        scales never calibrated against each other, so preferring one number over the other
        is arithmetic on incomparable quantities."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen(confidence=0.4)]),
            identify_species=lambda _: [_candidate("Mint", "Mentha spicata", 0.99)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["species"].common_name == "Basil"
        # And the node does not claim anybody agreed to it.
        assert result.get("species_confirmed") is not True

    def test_one_candidate_when_the_specialist_answers_nothing(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert [c.method for c in result["candidates"]] == [SpeciesMethod.VISION]


class TestWhenTheSecondOpinionCannotBeHad:
    def test_an_unconfigured_service_is_not_an_error(self, make_deps, sample_images):
        """No key returns nothing, exactly as a failure does. The node cannot tell, and is
        better for not having a branch on configuration in it."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert "errors" not in result

    def test_a_missing_photograph_fails_the_node_rather_than_quietly_using_fewer(
        self, make_deps, sample_images
    ):
        """This one is not caught, and should not be.

        A photograph missing from the store fails the *vision* call, before the second
        opinion is reached — `agent/vision.py` raises rather than skipping, because a
        diagnosis made from three of four photographs is one the owner believes was made
        from four. Recorded here so the guard around the second identification is not read
        as covering this: the two failures are at different depths and want different
        answers.
        """
        from uuid import uuid4

        from agent.vision import ImageMissingError

        deps = make_deps(vision_model=ScriptedStructuredModel([_seen()]))
        state = _state(sample_images)
        # A well-formed key with nothing behind it. A malformed one fails in the database
        # driver instead, which is a different bug and leaves the session unusable.
        state.images[0].ref = str(uuid4())

        with pytest.raises(ImageMissingError):
            make_identify_plant(deps)(state)

    def test_a_failing_identifier_does_not_fail_the_node(self, make_deps, sample_images):
        """The adapter answers every failure with an empty list, so this should be
        impossible — which is exactly why it is worth a test. A node that trusted that and
        was wrong would fail a diagnosis somebody paid for."""

        def _explodes(_photographs):
            raise RuntimeError("the adapter's guarantee did not hold")

        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=_explodes,
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["species"].common_name == "Basil"


class TestWhenSomebodyTypedTheSpecies:
    """The owner leads, and is still shown what the machines thought.

    A real trade, and worth naming where it is tested: the identification prompt tells the
    model to treat a supplied name as a hint precisely because people mislabel their plants.
    This makes that same name the default. What keeps it honest is the rest of this class —
    both methods still run, both answers survive, and the disagreement is one choice away
    from being settled the other way.
    """

    def test_what_was_typed_leads(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [_candidate("Thai basil", "Ocimum africanum", 0.71)],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species="Holy basil"))

        assert result["species"].common_name == "Holy basil"
        assert result["candidates"][0].method is SpeciesMethod.TYPED

    def test_both_methods_still_run(self, make_deps, sample_images):
        """The point of leading rather than deciding. A typed species that silenced the
        identifications would make a mislabel unfalsifiable."""
        model = ScriptedStructuredModel([_seen()])
        asked = []
        deps = make_deps(
            vision_model=model,
            identify_species=lambda photographs: (
                asked.append(photographs) or [_candidate("Thai basil", "Ocimum africanum", 0.71)]
            ),
        )

        make_identify_plant(deps)(_state(sample_images, stated_species="Holy basil"))

        assert model.call_count == 1
        assert len(asked) == 1

    def test_what_the_methods_concluded_survives_alongside_it(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [_candidate("Thai basil", "Ocimum africanum", 0.71)],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species="Holy basil"))

        assert [c.method for c in result["candidates"]] == [
            SpeciesMethod.TYPED,
            SpeciesMethod.VISION,
            SpeciesMethod.PLANTNET,
        ]

    def test_a_method_that_agrees_with_it_is_not_offered_twice(self, make_deps, sample_images):
        """Choosing between a thing and itself is not a choice."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen("Basil", None)]),
            identify_species=lambda _: [],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species="basil"))

        assert len(result["candidates"]) == 1
        assert result["candidates"][0].method is SpeciesMethod.TYPED

    def test_a_blank_species_is_not_a_species(self, make_deps, sample_images):
        """A form sends an empty string for a field somebody left alone. The router strips
        it to None, and this is the belt to that braces."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species=""))

        assert result["species"].common_name == "Basil"
        assert result["candidates"][0].method is SpeciesMethod.VISION


class TestWhatLeadsWithNothingTyped:
    def test_agreement_leads_over_a_lone_method(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [
                _candidate("Mint", "Mentha spicata", 0.99),
                _candidate("Sweet basil", "Ocimum basilicum", 0.30),
            ],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["candidates"][0].method is SpeciesMethod.AGREED
        assert result["species"].common_name == "Sweet basil"

    def test_the_vision_model_leads_when_nothing_agrees(self, make_deps, sample_images):
        """And specifically not the higher number: 0.99 from one method and 0.85 from
        another are not on the same scale, so choosing between them by size is arithmetic
        dressed up as a decision."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen(confidence=0.85)]),
            identify_species=lambda _: [_candidate("Mint", "Mentha spicata", 0.99)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert result["species"].common_name == "Basil"
        assert result["candidates"][0].method is SpeciesMethod.VISION


class TestWhenThereIsNothingToAsk:
    """Unanimity is the case that should cost the owner nothing.

    A choice screen offered when every method — and the owner — named the same plant is an
    interruption that asks somebody to confirm what nobody disputed. The rule the wizard
    reads is simply how many candidates there are: one means do not ask.
    """

    def test_all_three_agreeing_leaves_one_candidate(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen("Basil", "Ocimum basilicum")]),
            identify_species=lambda _: [_candidate("Sweet basil", "Ocimum basilicum", 0.9)],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species="Ocimum basilicum"))

        assert len(result["candidates"]) == 1

    def test_both_methods_agreeing_with_nothing_typed_leaves_one_candidate(
        self, make_deps, sample_images
    ):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen("Basil", "Ocimum basilicum")]),
            identify_species=lambda _: [_candidate("Sweet basil", "Ocimum basilicum", 0.9)],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert len(result["candidates"]) == 1
        assert result["candidates"][0].method is SpeciesMethod.AGREED

    def test_one_dissenter_is_enough_to_ask(self, make_deps, sample_images):
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen("Basil", "Ocimum basilicum")]),
            identify_species=lambda _: [_candidate("Mint", "Mentha spicata", 0.7)],
        )

        result = make_identify_plant(deps)(_state(sample_images, stated_species="Ocimum basilicum"))

        assert len(result["candidates"]) > 1

    def test_a_lone_method_is_also_nothing_to_ask(self, make_deps, sample_images):
        """No key, or a service that answered nothing. There is one answer and no dispute
        to put to anybody."""
        deps = make_deps(
            vision_model=ScriptedStructuredModel([_seen()]),
            identify_species=lambda _: [],
        )

        result = make_identify_plant(deps)(_state(sample_images))

        assert len(result["candidates"]) == 1
