"""The orchestration boundary between Streamlit and the agent.

The UI knows nothing about LangGraph, checkpointers, or resume commands. It calls
``start``, renders questions, calls ``answer``, and renders the result.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

from langgraph.types import Command

from agent.deps import Deps
from agent.schemas import (
    ContagionAssessment,
    Differential,
    ImageRef,
    Passage,
    Question,
    Roadmap,
    SpeciesGuess,
)
from agent.state import DiagnosisState
from core.cost import UsageCollector, UsageSnapshot
from core.images import store_upload
from services.profile_service import ProfileService

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
    """A completed diagnosis, ready to render.

    ``verdict``/``verdict_reasoning`` are flattened off ``ProgressVerdict`` rather than
    carrying the object: both are ``None`` for a first-time diagnosis, where no
    re-check comparison ever ran, and the UI only ever needs the two strings. They are
    render-only — nothing persists them, because nothing needs them after the
    post-submit rerun.
    """

    differential: Differential | None
    roadmap: Roadmap | None
    contagion: ContagionAssessment | None
    low_confidence: bool
    plant_id: UUID | None
    diagnosis_id: UUID | None
    retrieved: list[Passage]
    visual_matches: list[Passage]
    tools_used: list[str]
    errors: list[str]
    verdict: str | None = None
    verdict_reasoning: str | None = None
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None


class DiagnosisService:
    """Drives the diagnosis graph on behalf of the UI."""

    def __init__(
        self,
        deps: Deps,
        graph,
        *,
        upload_dir: Path,
        profile: ProfileService | None = None,
    ) -> None:
        self._deps = deps
        self._graph = graph
        self._upload_dir = upload_dir
        self._profile = profile
        # Keyed by thread_id because a diagnosis spans two invocations: start()
        # pauses at the clarifying-question interrupt and answer() resumes it. The
        # gate and vision calls all happen in the first, so a per-invoke collector
        # would undercount by roughly half. Evicted by _release() at every terminal
        # outcome, including an exception out of _graph.invoke, so a completed or
        # crashed run cannot leak. One case still leaks a single entry on purpose: a
        # session that paused for clarifying questions and was then abandoned before
        # answer() ever arrived. That entry is kept deliberately, not forgotten —
        # answer() may still resume the run at any time, and there is no
        # session-end signal here that would tell us it never will.
        self._collectors: dict[str, UsageCollector] = {}

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
        images = self._prepare_images(uploads)

        state = DiagnosisState(
            images=images,
            plant_name=plant_name,
            location_kind=location_kind,
            location_text=location_text,
            user_notes=user_notes,
        )

        # Wrapped rather than a blanket try/finally: the "questions" branch below is
        # a legitimate paused return that must keep its collector for answer() to
        # reuse, so only the exceptional exits release it — including the
        # RuntimeError raised when the graph finishes without interrupting.
        try:
            result = self._graph.invoke(state, self._run_config(thread_id))

            stopped = self._stopped_at_the_guards(result)
            if stopped is not None:
                self._release(thread_id)
                return stopped

            interrupts = result.get("__interrupt__") or []
            if not interrupts:
                logger.error("graph finished without interrupting and without rejecting")
                raise RuntimeError("The diagnosis could not be started. Please try again.")

            payload = interrupts[0].value
            questions = [Question.model_validate(q) for q in payload["questions"]]
            species = self._graph.get_state(self._config(thread_id)).values.get("species")
            return StartResult(status="questions", questions=questions, species=species)
        except Exception:
            self._release(thread_id)
            raise

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

        # Every exit from here is terminal for this thread — unlike start(), there
        # is no paused branch to preserve the collector for — so a plain
        # try/finally covers both the success path and any exception out of invoke.
        try:
            result = self._graph.invoke(Command(resume=answers), self._run_config(thread_id))
            final = self._final_result(result, self._collectors[thread_id].snapshot())
        finally:
            self._release(thread_id)

        # Fired after the diagnosis is fully committed and its collector released, so
        # nothing about learning can take either away from the owner. See the guard's
        # docstring on ProfileService for what this covers beyond extraction itself.
        if self._profile is not None:
            try:
                self._profile.learn_from_diagnosis(
                    answers=answers, location_text=result.get("location_text")
                )
            except Exception as exc:  # noqa: BLE001 — learning must never break a diagnosis
                logger.warning("profile learning failed: %s", exc)

        return final

    def start_recheck(
        self,
        *,
        plant_id: UUID,
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
        plant = self._deps.plants.get(self._deps.user_id, plant_id)
        if plant is None:
            raise ValueError(f"No plant with id {plant_id!r}.")

        images = self._prepare_images(uploads)

        state = DiagnosisState(
            images=images,
            plant_name=plant.name,
            location_kind=plant.location_kind,
            location_text=plant.location_text,
            user_notes=user_notes,
            plant_id=plant.id,
            # Left unset when the plant was never successfully identified, rather than
            # filled with an "Unknown" placeholder: the placeholder satisfied both
            # identify_plant's idempotency guard and the router's skip, so such a plant
            # could never acquire a species no matter how many re-checks it went
            # through. Unset routes this run through identify_plant instead.
            species=(
                SpeciesGuess(
                    common_name=plant.species,
                    scientific_name=None,
                    confidence=plant.species_confidence or 0.0,
                )
                if plant.species is not None
                else None
            ),
        )

        # Every exit here is terminal (a re-check never pauses for questions), so the
        # only thing to preserve against is an exception leaving the collector behind.
        try:
            result = self._graph.invoke(state, self._run_config(thread_id))

            stopped = self._stopped_at_the_guards(result)
            if stopped is not None:
                return stopped

            return self._final_result(result, self._collectors[thread_id].snapshot())
        finally:
            self._release(thread_id)

    def _prepare_images(self, uploads: list[bytes]) -> list[ImageRef]:
        """Validate the upload count and write the files to disk.

        Shared by ``start`` and ``start_recheck``: both entry points feed the same
        guards, and a limit enforced in only one of them would be a hole.

        Raises:
            ValueError: if the upload count is outside the allowed range.
            UploadRejected: if any upload fails validation.
        """
        settings = self._deps.settings
        if not uploads:
            raise ValueError("Please upload at least one photo.")
        if len(uploads) > settings.max_images_per_observation:
            raise ValueError(f"Please upload at most {settings.max_images_per_observation} photos.")
        return [store_upload(data, self._upload_dir, settings) for data in uploads]

    @staticmethod
    def _stopped_at_the_guards(result: dict) -> StartResult | None:
        """The intake guards' verdict on a finished run, or ``None`` to keep reading it.

        ``guard_input`` and ``quality_check`` are shared by both entry points, so both
        can end this way; ``None`` means neither guard stopped the run.
        """
        if result.get("rejected"):
            return StartResult(status="rejected", message=result.get("rejection_reason") or "")

        quality = result.get("quality")
        if quality is not None and not quality.usable:
            return StartResult(
                status="retake", message=quality.guidance or "Please upload a clearer photo."
            )

        return None

    def _final_result(self, result: dict, usage: UsageSnapshot | None = None) -> FinalResult:
        # A ProgressVerdict for a re-check, absent for a first-time diagnosis.
        verdict = result.get("verdict")
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
            verdict=verdict.verdict if verdict is not None else None,
            verdict_reasoning=verdict.reasoning if verdict is not None else None,
            token_usage=usage.as_token_usage() if usage else None,
            cost_usd=usage.cost_usd if usage else None,
        )

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _run_config(self, thread_id: str) -> dict:
        """Config for an ``invoke``, carrying this thread's usage collector.

        The collector is passed twice deliberately: as a callback, so it observes
        every model call without any node knowing it exists, and through
        ``configurable``, so ``persist`` can read it (spec §2.1).
        """
        collector = self._collectors.setdefault(thread_id, UsageCollector())
        return {
            "configurable": {"thread_id": thread_id, "usage_collector": collector},
            "callbacks": [collector],
        }

    def _release(self, thread_id: str) -> None:
        """Drop a finished thread's collector."""
        self._collectors.pop(thread_id, None)
