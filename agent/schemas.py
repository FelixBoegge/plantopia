"""Every Pydantic contract in the application.

These schemas are the interface between the model and the code. Their validators
are deliberately strict: a node test that asserts on structure is only meaningful
if the structure is actually enforced here.
"""

from enum import IntEnum, StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


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


class ImageQuality(BaseModel):
    usable: bool
    problem: str | None = None
    guidance: str | None = None


class PlantCheck(BaseModel):
    """Whether the uploaded images show plant material."""

    is_plant: bool
    what_it_is: str = Field(min_length=1, description="Short description of what the image shows")


class Question(BaseModel):
    key: str = Field(min_length=1)
    text: str = Field(min_length=5)
    kind: Literal["text", "choice", "boolean"]
    options: list[str] = Field(default_factory=list)

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
    """One uploaded image, carried through the graph as base64.

    Defined here rather than in ``agent/state.py`` because the retriever needs it and
    must not depend on graph state.
    """

    ref: str
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_b64: str


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
