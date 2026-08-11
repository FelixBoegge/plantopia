"""Orchestration for the plant-profile pages: My Plants and Plant detail.

Follows the same rule as ``services/diagnosis_service.py``: the UI calls this and
nothing lower — no repository, and no direct SQL, in ``ui/``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from data.db import transaction
from data.repositories.diagnoses import DiagnosisRecord, DiagnosisRepository
from data.repositories.feedback import DidItHelp, FeedbackRepository
from data.repositories.observations import ObservationRecord, ObservationRepository
from data.repositories.plants import PlantRecord, PlantRepository
from data.repositories.roadmap import RoadmapRepository, RoadmapStepRecord, StepStatus


@dataclass(frozen=True, slots=True)
class PlantSummary:
    """One row on the My Plants grid."""

    plant: PlantRecord
    latest_diagnosis: DiagnosisRecord | None
    pending_step_count: int


@dataclass(frozen=True, slots=True)
class PlantDetail:
    """Everything the Plant detail page renders."""

    plant: PlantRecord
    observations: list[ObservationRecord]
    diagnoses: list[DiagnosisRecord]
    roadmap_steps: list[RoadmapStepRecord]
    feedback_due: bool


class PlantService:
    """Read and write access to plant profiles, for the UI."""

    def __init__(
        self,
        *,
        plants: PlantRepository,
        observations: ObservationRepository,
        diagnoses: DiagnosisRepository,
        roadmap: RoadmapRepository,
        feedback: FeedbackRepository,
        now: Callable[[], datetime],
    ) -> None:
        self._plants = plants
        self._observations = observations
        self._diagnoses = diagnoses
        self._roadmap = roadmap
        self._feedback = feedback
        self._now = now

    def list_plants(self) -> list[PlantSummary]:
        """Every plant, newest first, with its latest diagnosis and pending step count."""
        summaries = []
        for plant in self._plants.list_all():
            latest = self._diagnoses.latest_for_plant(plant.id)
            pending = sum(
                1 for s in self._roadmap.list_for_plant(plant.id) if s.status == "pending"
            )
            summaries.append(
                PlantSummary(plant=plant, latest_diagnosis=latest, pending_step_count=pending)
            )
        return summaries

    def get_plant_detail(self, plant_id: int) -> PlantDetail | None:
        """Everything the Plant detail page needs, or ``None`` for an unknown plant."""
        plant = self._plants.get(plant_id)
        if plant is None:
            return None

        observations = self._observations.list_for_plant(plant_id)
        diagnoses_list = self._diagnoses.list_for_plant(plant_id)
        roadmap_steps = self._roadmap.list_for_plant(plant_id)
        latest_diagnosis = diagnoses_list[0] if diagnoses_list else None

        feedback_due = (
            latest_diagnosis is not None
            and not self._feedback.exists_for_diagnosis(latest_diagnosis.id)
            and any(
                step.status == "done"
                for step in roadmap_steps
                if step.diagnosis_id == latest_diagnosis.id
            )
        )

        return PlantDetail(
            plant=plant,
            observations=observations,
            diagnoses=diagnoses_list,
            roadmap_steps=roadmap_steps,
            feedback_due=feedback_due,
        )

    def mark_roadmap_step(self, step_id: int, *, status: StepStatus) -> None:
        """Tick, skip, or reopen a roadmap step."""
        with transaction(self._roadmap.connection):
            self._roadmap.mark(step_id, status=status, now=self._now())

    def submit_feedback(
        self,
        *,
        diagnosis_id: int,
        rating: int | None,
        did_it_help: DidItHelp | None,
        free_text: str | None,
    ) -> int:
        with transaction(self._feedback.connection):
            return self._feedback.create(
                diagnosis_id=diagnosis_id,
                rating=rating,
                did_it_help=did_it_help,
                free_text=free_text,
                now=self._now(),
            )
