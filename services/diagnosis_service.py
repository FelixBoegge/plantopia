"""The orchestration boundary between Streamlit and the agent.

The UI knows nothing about LangGraph, checkpointers, or resume commands. It calls
``start``, renders questions, calls ``answer``, and renders the result.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from langgraph.types import Command

from agent.deps import Deps
from agent.schemas import (
    ContagionAssessment,
    Differential,
    Passage,
    Question,
    Roadmap,
    SpeciesGuess,
)
from agent.state import DiagnosisState
from core.images import store_upload

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StartResult:
    """What happened when a diagnosis was started."""

    status: Literal["questions", "rejected", "retake"]
    questions: list[Question] = field(default_factory=list)
    species: SpeciesGuess | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class FinalResult:
    """A completed diagnosis, ready to render."""

    differential: Differential | None
    roadmap: Roadmap | None
    contagion: ContagionAssessment | None
    low_confidence: bool
    plant_id: int | None
    diagnosis_id: int | None
    retrieved: list[Passage]
    visual_matches: list[Passage]
    tools_used: list[str]
    errors: list[str]


class DiagnosisService:
    """Drives the diagnosis graph on behalf of the UI."""

    def __init__(self, deps: Deps, graph, *, upload_dir: Path) -> None:
        self._deps = deps
        self._graph = graph
        self._upload_dir = upload_dir

    def start(
        self,
        *,
        uploads: list[bytes],
        plant_name: str,
        location_kind: Literal["indoor", "outdoor"],
        location_text: str | None,
        user_notes: str | None,
        thread_id: str,
    ) -> StartResult:
        """Validate uploads and run the graph until it asks for input.

        Raises:
            ValueError: if the upload count is outside the allowed range.
            UploadRejected: if any upload fails validation.
        """
        settings = self._deps.settings

        if not uploads:
            raise ValueError("Please upload at least one photo.")
        if len(uploads) > settings.max_images_per_observation:
            raise ValueError(f"Please upload at most {settings.max_images_per_observation} photos.")

        images = [store_upload(data, self._upload_dir, settings) for data in uploads]

        state = DiagnosisState(
            images=images,
            plant_name=plant_name,
            location_kind=location_kind,
            location_text=location_text,
            user_notes=user_notes,
        )

        result = self._graph.invoke(state, self._config(thread_id))

        if result.get("rejected"):
            return StartResult(status="rejected", message=result.get("rejection_reason") or "")

        quality = result.get("quality")
        if quality is not None and not quality.usable:
            message = quality.guidance or "Please upload a clearer photo."
            return StartResult(status="retake", message=message)

        interrupts = result.get("__interrupt__") or []
        if not interrupts:
            logger.error("graph finished without interrupting and without rejecting")
            raise RuntimeError("The diagnosis could not be started. Please try again.")

        payload = interrupts[0].value
        questions = [Question.model_validate(q) for q in payload["questions"]]
        species = self._graph.get_state(self._config(thread_id)).values.get("species")
        return StartResult(status="questions", questions=questions, species=species)

    def answer(
        self,
        answers: dict[str, str],
        *,
        thread_id: str,
        species_override: str | None = None,
    ) -> FinalResult:
        """Resume the paused graph with the user's answers and return the diagnosis.

        Args:
            answers: Responses to the clarifying questions.
            thread_id: The paused run to resume.
            species_override: A species the user corrected. Treated as certain — the
                owner knows their own plant better than a photograph does.

        Raises:
            ValueError: if no paused run exists for this thread.
        """
        config = self._config(thread_id)

        snapshot = self._graph.get_state(config)
        if not snapshot.created_at:
            raise ValueError(f"No diagnosis in progress for thread {thread_id!r}.")

        if species_override and species_override.strip():
            corrected = SpeciesGuess(
                common_name=species_override.strip(),
                scientific_name=None,
                confidence=1.0,
            )
            self._graph.update_state(config, {"species": corrected})
            logger.info("species corrected by the user to %r", corrected.common_name)

        result = self._graph.invoke(Command(resume=answers), config)
        return self._final_result(result)

    def start_recheck(
        self,
        *,
        plant_id: int,
        uploads: list[bytes],
        user_notes: str | None,
        thread_id: str,
    ) -> StartResult | FinalResult:
        """Start a re-check run against an existing plant's prior diagnosis.

        Unlike ``start``, species and location come from the existing plant record
        rather than being asked for, and the run never pauses for clarifying
        questions — roadmap-step completion already answers what a re-check would
        otherwise have to ask (see the design spec §3).

        Raises:
            ValueError: if the plant does not exist, or the upload count is outside
                the allowed range.
        """
        settings = self._deps.settings
        plant = self._deps.plants.get(plant_id)
        if plant is None:
            raise ValueError(f"No plant with id {plant_id!r}.")

        if not uploads:
            raise ValueError("Please upload at least one photo.")
        if len(uploads) > settings.max_images_per_observation:
            raise ValueError(f"Please upload at most {settings.max_images_per_observation} photos.")

        images = [store_upload(data, self._upload_dir, settings) for data in uploads]

        state = DiagnosisState(
            images=images,
            plant_name=plant.name,
            location_kind=plant.location_kind,
            location_text=plant.location_text,
            user_notes=user_notes,
            plant_id=plant.id,
            species=SpeciesGuess(
                common_name=plant.species or "Unknown",
                scientific_name=None,
                confidence=plant.species_confidence or 0.0,
            ),
        )

        result = self._graph.invoke(state, self._config(thread_id))

        if result.get("rejected"):
            return StartResult(status="rejected", message=result.get("rejection_reason") or "")

        quality = result.get("quality")
        if quality is not None and not quality.usable:
            message = quality.guidance or "Please upload a clearer photo."
            return StartResult(status="retake", message=message)

        return self._final_result(result)

    def _final_result(self, result: dict) -> FinalResult:
        return FinalResult(
            differential=result.get("differential"),
            roadmap=result.get("roadmap"),
            contagion=result.get("contagion"),
            low_confidence=bool(result.get("low_confidence")),
            plant_id=result.get("plant_id"),
            diagnosis_id=result.get("diagnosis_id"),
            retrieved=result.get("retrieved") or [],
            visual_matches=result.get("visual_matches") or [],
            tools_used=result.get("tools_used") or [],
            errors=result.get("errors") or [],
        )

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}
