"""Every Pydantic contract in the application.

These schemas are the interface between the model and the code. Their validators
are deliberately strict: a node test that asserts on structure is only meaningful
if the structure is actually enforced here.
"""

from enum import IntEnum, StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class SymptomPosition(StrEnum):
    """Where on the plant a symptom appears.

    Position is the single most diagnostic feature — interveinal yellowing means
    something quite different from yellowing that starts at the leaf tip — so it is
    a required field rather than free text.
    """

    LEAF_TIP = "leaf_tip"
    LEAF_MARGIN = "leaf_margin"
    INTERVEINAL = "interveinal"
    WHOLE_LEAF = "whole_leaf"
    LOWER_LEAVES = "lower_leaves"
    NEW_GROWTH = "new_growth"
    STEM = "stem"
    SOIL_SURFACE = "soil_surface"
    ROOTS = "roots"
    WHOLE_PLANT = "whole_plant"


class ImageOrgan(StrEnum):
    """Which part of the plant a photograph shows.

    The vocabulary is not ours. Pl@ntNet accepts the organ as an input and is markedly more
    accurate given it, so these are the values *it* recognises — which is why they are here
    rather than being folded into ``SymptomPosition``, whose vocabulary is about where a
    symptom appears and answers a different question.

    ``UNKNOWN`` is ours, and is the only member that is not sent. A photograph whose organ
    the vision model cannot determine is sent without a claimed organ; guessing one would
    feed a specialist classifier a wrong hint, which is worse than no hint.
    """

    LEAF = "leaf"
    FLOWER = "flower"
    FRUIT = "fruit"
    BARK = "bark"
    HABIT = "habit"
    UNKNOWN = "unknown"


class SpeciesMethod(StrEnum):
    """What produced a species candidate.

    Carried with every candidate because a name on its own cannot be argued with. Knowing
    that the vision model and the specialist classifier disagree — and which said what — is
    the whole reason the choice is worth putting to somebody.
    """

    TYPED = "typed"  # The person starting the diagnosis said so.
    VISION = "vision"  # The general-purpose vision model's guess.
    PLANTNET = "plantnet"  # The specialist identification service.
    AGREED = "agreed"  # Vision and the service named the same species.


class Severity(StrEnum):
    """How urgently the user needs to act."""

    MONITOR = "monitor"
    ACT_THIS_WEEK = "act_this_week"
    ACT_TODAY = "act_today"


class IPMTier(IntEnum):
    """Integrated pest management escalation tiers. Lower is less invasive."""

    CULTURAL = 1
    MECHANICAL = 2
    BIOLOGICAL = 3
    CHEMICAL = 4


class Symptom(BaseModel):
    description: str = Field(min_length=3)
    position: SymptomPosition
    severity: Severity


class SymptomSet(BaseModel):
    symptoms: list[Symptom] = Field(min_length=1)
    soil_condition: str | None = None
    overall_vigor: Literal["good", "declining", "poor"]


class SpeciesGuess(BaseModel):
    common_name: str = Field(min_length=1)
    scientific_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class VisionIdentification(BaseModel):
    """What the vision model reports after looking at the photographs.

    The species *and* what each photograph shows, in one response. Flat rather than nested
    because a model asked for a nested object gets it wrong more often, and one call rather
    than two because the organs exist to be sent to a second identifier — a separate call to
    tag them would add model spend to save a second or two of a ninety-second run.

    ``organs`` is positional: one entry per photograph, in the order they were supplied.
    """

    common_name: str = Field(min_length=1)
    scientific_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    organs: list[ImageOrgan] = Field(default_factory=list)

    @field_validator("organs", mode="before")
    @classmethod
    def _tolerate_an_unknown_organ(cls, value: object) -> object:
        """Coerce an organ outside the vocabulary rather than rejecting the whole response.

        Strict validation is right almost everywhere in this file, and wrong here. The organ
        is a hint for a second identifier; the species is the answer. Refusing the response
        because the model called something a "stem" would throw away a good identification
        over a bad hint — so an unrecognised value becomes ``UNKNOWN``, which is the value
        that is deliberately never sent.
        """
        if not isinstance(value, list):
            return value

        known = {organ.value for organ in ImageOrgan}
        return [
            item if isinstance(item, ImageOrgan) or item in known else ImageOrgan.UNKNOWN
            for item in value
        ]

    def species(self) -> "SpeciesGuess":
        """The identification alone, for the state field that only wants that."""
        return SpeciesGuess(
            common_name=self.common_name,
            scientific_name=self.scientific_name,
            confidence=self.confidence,
        )

    def organ_for(self, index: int) -> ImageOrgan:
        """The organ of the photograph at ``index``, or unknown.

        Tolerant of a model that returned the wrong number of organs, which is a thing they
        do: too few and the rest are unknown, too many and the extras are ignored. Neither
        is worth failing an identification over.
        """
        try:
            return self.organs[index]
        except IndexError:
            return ImageOrgan.UNKNOWN


class SpeciesCandidate(BaseModel):
    """One answer to "what is this plant?", with where it came from.

    ``method`` has no default on purpose. A candidate whose provenance is unstated is a
    candidate nobody can weigh, and defaulting it would let one be constructed by accident
    at exactly the site where somebody forgot to say.
    """

    common_name: str = Field(min_length=1)
    scientific_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    method: SpeciesMethod


class Hypotheses(BaseModel):
    """Disorders worth looking up, named from the symptoms before reading the corpus.

    Ids rather than free text, drawn from a list supplied in the prompt, so each one
    is a document that can be fetched directly. The point of the step is to reach
    documents that similarity search ranks too low to return — measured at 16th, 17th
    and 21st of 43 for three nutrient cases — which requires naming them, not
    describing them.
    """

    doc_ids: list[str] = Field(default_factory=list, max_length=8)
    reasoning: str = ""


class ImageQuality(BaseModel):
    usable: bool
    problem: str | None = None
    guidance: str | None = None


class PlantCheck(BaseModel):
    """Whether the uploaded images show plant material."""

    is_plant: bool
    what_it_is: str = Field(min_length=1, description="Short description of what the image shows")


class Question(BaseModel):
    """One thing the agent needs to know before it can go on.

    ``prefill`` is an answer the system already believes — a place read from a photograph,
    say. It is offered *as the answer* rather than as a suggestion beside an empty field,
    because that is what it is: it will be used unless somebody says otherwise. A suggestion
    asks the common case to do work; a filled field asks only the uncommon one.

    ``required`` refuses a submission that leaves the field empty. Almost nothing is: a
    question somebody cannot answer is a question they should be able to skip, and the one
    exception is where the answer's absence costs a real part of the diagnosis.
    """

    key: str = Field(min_length=1)
    text: str = Field(min_length=5)
    kind: Literal["text", "choice", "boolean"]
    options: list[str] = Field(default_factory=list)
    prefill: str | None = None
    required: bool = False

    @model_validator(mode="after")
    def _choice_needs_options(self) -> Self:
        if self.kind == "choice" and len(self.options) < 2:
            raise ValueError("a choice question needs at least two options")
        return self


class QuestionSet(BaseModel):
    """Clarifying questions selected for one case."""

    questions: list[Question] = Field(default_factory=list)


class Passage(BaseModel):
    doc_id: str
    section: str
    text: str
    score: float = Field(ge=0.0, le=1.0)


class ImageRef(BaseModel):
    """One uploaded image, carried through the graph as a key.

    Deliberately *not* the bytes. LangGraph re-serialises the whole state at every
    superstep, so an image held here is written to the checkpoint once per node —
    ``M15`` measured 205 MB of checkpoint blobs from two diagnoses of 3 MB
    photographs. The bytes are loaded from the blob store at the one place that needs
    them, the vision call.

    Defined here rather than in ``agent/state.py`` because the retriever needs it and
    must not depend on graph state.
    """

    ref: UUID
    media_type: Literal["image/png", "image/jpeg", "image/webp"]


class LoadedImage(BaseModel):
    """An image with its bytes in hand.

    Distinct from ``ImageRef`` on purpose. A reference is what travels through graph
    state; this is what exists briefly at the two boundaries that need real pixels —
    the vision call and, when an embedder can accept one, the cross-modal search.
    Keeping them separate is what stops bytes drifting back into state (``M15``).
    """

    model_config = {"arbitrary_types_allowed": True}

    data: bytes
    media_type: Literal["image/png", "image/jpeg", "image/webp"]


class CareProfile(BaseModel):
    species: str
    light: str
    water: str
    temperature_c: tuple[int, int]
    humidity: str


class WeatherSummary(BaseModel):
    min_temp_c: float
    max_temp_c: float
    total_precip_mm: float
    frost_days: int = Field(ge=0)
    heat_days: int = Field(ge=0)
    days_covered: int = Field(gt=0)


class Candidate(BaseModel):
    disorder_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(min_length=1)
    contradicting_evidence: list[str] = Field(default_factory=list)
    distinguishing_test: str = Field(min_length=15)
    severity: Severity
    transmissible: bool


class Differential(BaseModel):
    """A ranked set of candidate causes, or an explicit finding of health.

    A healthy plant is a valid outcome. The agent must not manufacture a problem
    in order to feel useful (spec §14).
    """

    is_healthy: bool = False
    candidates: list[Candidate] = Field(default_factory=list)
    reasoning: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_candidates(self) -> Self:
        if self.is_healthy:
            if self.candidates:
                raise ValueError("a healthy differential must have no candidates")
            return self

        if not 2 <= len(self.candidates) <= 3:
            raise ValueError("an unhealthy differential needs between two and three candidates")

        probabilities = [c.probability for c in self.candidates]
        if probabilities != sorted(probabilities, reverse=True):
            raise ValueError("candidates must be sorted by probability, descending")

        ids = [c.disorder_id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("candidates must be distinct disorders")
        return self

    @property
    def top_confidence(self) -> float:
        """Probability of the leading candidate, or 0.0 for a healthy plant."""
        return self.candidates[0].probability if self.candidates else 0.0

    @property
    def primary(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


class ContagionAssessment(BaseModel):
    at_risk: bool
    advice: str


class ProgressVerdict(BaseModel):
    """The result of comparing a re-check photo against the prior diagnosis.

    Compliance is not a field here: roadmap-step completion is already recorded by
    ``RoadmapRepository``, so the model reads it from the prompt rather than being
    asked to report it back.
    """

    verdict: Literal["improving", "static", "worsening", "new_problem"]
    reasoning: str = Field(min_length=1)


class RoadmapStep(BaseModel):
    ordinal: int = Field(ge=1)
    action: str = Field(min_length=5)
    rationale: str = Field(min_length=5)
    success_signal: str = Field(min_length=5)
    tier: IPMTier
    day_offset: int = Field(ge=0, description="Days from the diagnosis date until this step is due")


class Roadmap(BaseModel):
    """Treatment steps, ordered by IPM escalation (spec §13.5)."""

    steps: list[RoadmapStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        ordinals = [s.ordinal for s in self.steps]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("step ordinals must be sequential starting at 1")

        tiers = [int(s.tier) for s in self.steps]
        if tiers != sorted(tiers):
            raise ValueError(
                "steps must escalate: a more invasive tier cannot precede a less invasive one"
            )
        return self


class ExtractedFact(BaseModel):
    """One durable fact about the owner, as the extraction model reports it.

    Distinct from ``data.repositories.profile.ProfileFact``, which is the stored
    row: this one has no timestamps because the service assigns them.
    """

    fact: str = Field(min_length=3, max_length=200)
    source: Literal["inferred", "stated"]
    confidence: float = Field(ge=0.0, le=1.0)


class ProfileUpdate(BaseModel):
    """The reconciliation the model returns against the current profile.

    ``confirmed`` and ``superseded`` hold existing facts echoed *verbatim*, not
    paraphrased: ``user_profile.fact`` is UNIQUE over free text, so exact echoes
    are what let the constraint deduplicate instead of accumulating five
    phrasings of one habit.
    """

    confirmed: list[str] = Field(default_factory=list)
    added: list[ExtractedFact] = Field(default_factory=list)
    superseded: list[str] = Field(default_factory=list)
