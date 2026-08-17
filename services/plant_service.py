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
        """Every plant, newest first, with its latest diagnosis and pending step count.

        The count is scoped to the latest diagnosis's own plan, for the same reason
        ``get_plant_detail`` scopes the checklist: counting every step ever created
        made the badge climb monotonically with each re-check.
        """
        summaries = []
        for plant in self._plants.list_all():
            latest = self._diagnoses.latest_for_plant(plant.id)
            pending = sum(
                1
                for s in self._steps_for_latest_diagnosis(plant.id, latest)
                if s.status == "pending"
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
        latest_diagnosis = diagnoses_list[0] if diagnoses_list else None
        roadmap_steps = self._steps_for_latest_diagnosis(plant_id, latest_diagnosis)

        feedback_due = (
            latest_diagnosis is not None
            and not self._feedback.exists_for_diagnosis(latest_diagnosis.id)
            and any(step.status == "done" for step in roadmap_steps)
        )

        return PlantDetail(
            plant=plant,
            observations=observations,
            diagnoses=diagnoses_list,
            roadmap_steps=roadmap_steps,
            feedback_due=feedback_due,
        )

    def _steps_for_latest_diagnosis(
        self, plant_id: int, latest_diagnosis: DiagnosisRecord | None
    ) -> list[RoadmapStepRecord]:
        """This plant's current plan only.

        ``RoadmapRepository.list_for_plant`` returns every step ever created for the
        plant, across every diagnosis and every re-check — and a re-check always writes
        a whole new roadmap (design decision P2-4). Unscoped, the checklist mixed
        superseded plans in with the current one, all still tickable, and the pending
        count summed across all of them.

        Steps from older diagnoses stay in the database untouched; they remain visible
        through that diagnosis's timeline entry, just not as live checkboxes.
        """
        if latest_diagnosis is None:
            return []
        return [
            step
            for step in self._roadmap.list_for_plant(plant_id)
            if step.diagnosis_id == latest_diagnosis.id
        ]

    def rename_plant(self, plant_id: int, *, name: str) -> None:
        """Give a plant the name its owner confirmed after identification.

        Blank input is rejected here rather than in the page: a plant with an empty
        name would render as an unlabelled card with no way back to fix it.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("A plant needs a name.")
        with transaction(self._plants.connection):
            self._plants.rename(plant_id, name=cleaned)

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
