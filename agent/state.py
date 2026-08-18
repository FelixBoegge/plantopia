"""The diagnosis graph's state.

LangGraph accepts a Pydantic model as a state schema. Nodes return dicts holding
only the keys they changed; LangGraph merges them.
"""

from typing import Literal

from pydantic import BaseModel, Field

from agent.schemas import (
    ContagionAssessment,
    Differential,
    ImageQuality,
    ImageRef,
    Passage,
    ProgressVerdict,
    Question,
    Roadmap,
    SpeciesGuess,
    SymptomSet,
    WeatherSummary,
)

__all__ = ["DiagnosisState", "ImageRef"]


class DiagnosisState(BaseModel):
    """Everything the diagnosis pipeline reads and writes."""

    # Inputs
    images: list[ImageRef] = Field(min_length=1)
    plant_name: str
    location_kind: Literal["indoor", "outdoor"]
    location_text: str | None = None
    user_notes: str | None = None
    plant_id: int | None = None

    # Intake results
    rejected: bool = False
    rejection_reason: str | None = None
    quality: ImageQuality | None = None

    # Analysis
    species: SpeciesGuess | None = None
    symptoms: SymptomSet | None = None

    # Human in the loop
    questions: list[Question] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)

    # Disorders the model named as worth reading about, before any retrieval ran.
    # Kept on state rather than passed straight to enrich so the trace, and Studio,
    # show what the agent chose to look up and the diagnosis can be read against it.
    hypotheses: list[str] = Field(default_factory=list)

    # Enrichment — the two retrieval paths are kept separate on purpose. Their scores
    # are not comparable, so they must never be merged into one ranked list (§10.4).
    retrieved: list[Passage] = Field(default_factory=list)
    visual_matches: list[Passage] = Field(default_factory=list)
    weather: WeatherSummary | None = None
    care_baseline_text: str | None = None
    escalated_to_web: bool = False

    # Conclusions
    differential: Differential | None = None
    low_confidence: bool = False
    contagion: ContagionAssessment | None = None
    roadmap: Roadmap | None = None
    verdict: ProgressVerdict | None = None

    # Bookkeeping
    observation_id: int | None = None
    diagnosis_id: int | None = None
    tools_used: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def species_confidence(self) -> float:
        """Confidence in the species identification, or 0.0 if unidentified."""
        return self.species.confidence if self.species else 0.0

    @property
    def species_name(self) -> str | None:
        return self.species.common_name if self.species else None
