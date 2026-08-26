"""The diagnosis graph's state.

LangGraph accepts a Pydantic model as a state schema. Nodes return dicts holding
only the keys they changed; LangGraph merges them.
"""

from typing import Literal
from uuid import UUID

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
    SpeciesCandidate,
    SpeciesGuess,
    SpeciesMethod,
    SymptomSet,
    WeatherSummary,
)

__all__ = ["DiagnosisState", "ImageRef"]


class DiagnosisState(BaseModel):
    """Everything the diagnosis pipeline reads and writes."""

    # Inputs
    images: list[ImageRef] = Field(min_length=1)
    plant_name: str

    # What the owner says the plant is, if they said. A name is not a species: "Kitchen
    # basil" is what somebody calls their plant and "Ocimum basilicum" is what it is, and
    # conflating them is how a nickname ends up being searched for in a disorder corpus.
    stated_species: str | None = None

    location_kind: Literal["indoor", "outdoor"]
    location_text: str | None = None
    user_notes: str | None = None
    plant_id: UUID | None = None

    # Intake results
    rejected: bool = False
    rejection_reason: str | None = None
    quality: ImageQuality | None = None

    # Analysis
    species: SpeciesGuess | None = None

    # Every answer to "what is this plant?", with the method that produced each. The
    # species above is whichever of these is currently believed; this is the working out.
    # Kept because two methods disagreeing is information — it is what the owner is shown
    # at the pause, and what makes a wrong diagnosis attributable afterwards.
    candidates: list[SpeciesCandidate] = Field(default_factory=list)

    # Whether a person picked the species, as opposed to it being the best guess going.
    species_confirmed: bool = False

    # Which method produced the species above. Carried rather than derived at the end,
    # because by then the only way back to it is matching a name against the candidate list
    # — and a diagnosis's provenance should not rest on string comparison run an hour later.
    species_method: SpeciesMethod | None = None

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
    observation_id: UUID | None = None
    diagnosis_id: UUID | None = None
    tools_used: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def species_confidence(self) -> float:
        """Confidence in the species identification, or 0.0 if unidentified."""
        return self.species.confidence if self.species else 0.0

    @property
    def species_name(self) -> str | None:
        return self.species.common_name if self.species else None
