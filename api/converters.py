"""Storage records to response schemas.

One place, so that a field appearing in the API is a decision made here rather than a
consequence of a column existing. Every function is total: given a record it returns a
response, and it never reaches back into the database.
"""

from collections.abc import Sequence

from api.schemas import (
    CandidateOut,
    DiagnosisOut,
    MessageOut,
    ObservationOut,
    PlantDetailOut,
    PlantOut,
    PlantSummaryOut,
    ProfileFactOut,
    RoadmapStepOut,
    RunOut,
    SourceOut,
    TokenUsageOut,
)
from data.repositories.diagnoses import DiagnosisRecord
from data.repositories.messages import MessageRecord
from data.repositories.observations import ObservationRecord
from data.repositories.plants import PlantRecord
from data.repositories.profile import ProfileFact
from data.repositories.roadmap import RoadmapStepRecord
from services.plant_service import PlantDetail, PlantSummary, Source


def plant(record: PlantRecord) -> PlantOut:
    return PlantOut(
        id=record.id,
        name=record.name,
        species=record.species,
        species_confidence=record.species_confidence,
        location_kind=record.location_kind,
        location_text=record.location_text,
        photo_ref=record.photo_ref,
        created_at=record.created_at,
    )


def diagnosis(record: DiagnosisRecord, sources: Sequence[Source] = ()) -> DiagnosisOut:
    """The differential, flattened.

    Candidates are lifted out of the stored JSON rather than passed through it: a client
    should not have to know that a differential is serialised, and the stored blob carries
    fields the API has no reason to publish.

    ``sources`` is passed in rather than read from ``record.retrieved`` here, even though
    the passages are on the record: naming a disorder takes a query, and this function is
    pure. It defaults to empty so a caller with no use for them — or no session to look
    them up with — is not obliged to produce any.
    """
    return DiagnosisOut(
        id=record.id,
        plant_id=record.plant_id,
        observation_id=record.observation_id,
        species_method=record.species_method,
        progress_verdict=record.progress_verdict,
        species_confirmed=record.species_confirmed,
        token_usage=(TokenUsageOut(**record.token_usage) if record.token_usage else None),
        sources=[
            SourceOut(name=source.name, section=source.section, origin=source.origin)
            for source in sources
        ],
        is_healthy=record.differential.is_healthy,
        reasoning=record.differential.reasoning,
        candidates=[
            CandidateOut(
                disorder_id=candidate.disorder_id,
                name=candidate.name,
                probability=candidate.probability,
                severity=candidate.severity.value,
                supporting_evidence=list(candidate.supporting_evidence),
                contradicting_evidence=list(candidate.contradicting_evidence),
                distinguishing_test=candidate.distinguishing_test,
            )
            for candidate in record.differential.candidates
        ],
        created_at=record.created_at,
        cost_usd=record.cost_usd,
        weather=record.weather,
    )


def observation(record: ObservationRecord) -> ObservationOut:
    return ObservationOut(
        id=record.id,
        plant_id=record.plant_id,
        kind=record.kind,
        photo_refs=list(record.photo_refs),
        user_notes=record.user_notes,
        created_at=record.created_at,
        # What the observation knows about itself. All four were on the record or the row
        # and none of them were readable: the weather was dropped here, and the capture date
        # and position stopped one layer earlier. A timeline's spine is observations, so
        # this is where they have to arrive.
        captured_at=record.captured_at,
        latitude=record.latitude,
        longitude=record.longitude,
        weather=record.weather,
    )


def roadmap_step(record: RoadmapStepRecord) -> RoadmapStepOut:
    return RoadmapStepOut(
        id=record.id,
        diagnosis_id=record.diagnosis_id,
        ordinal=record.ordinal,
        action=record.action,
        rationale=record.rationale,
        success_signal=record.success_signal,
        tier=int(record.tier),
        due_date=record.due_date,
        status=record.status,
        completed_at=record.completed_at,
    )


def message(record: MessageRecord) -> MessageOut:
    return MessageOut(
        id=record.id,
        plant_id=record.plant_id,
        role=record.role,
        content=record.content,
        tool_calls=record.tool_calls,
        created_at=record.created_at,
    )


def profile_fact(record: ProfileFact) -> ProfileFactOut:
    return ProfileFactOut(
        fact=record.fact,
        source=record.source,
        confidence=record.confidence,
        first_seen=record.first_seen,
        last_confirmed=record.last_confirmed,
    )


def plant_summary(summary: PlantSummary) -> PlantSummaryOut:
    return PlantSummaryOut(
        plant=plant(summary.plant),
        latest_diagnosis=diagnosis(summary.latest_diagnosis) if summary.latest_diagnosis else None,
        pending_step_count=summary.pending_step_count,
    )


def plant_detail(detail: PlantDetail) -> PlantDetailOut:
    return PlantDetailOut(
        plant=plant(detail.plant),
        observations=[observation(o) for o in detail.observations],
        diagnoses=[diagnosis(d) for d in detail.diagnoses],
        roadmap_steps=[roadmap_step(s) for s in detail.roadmap_steps],
        feedback_due=detail.feedback_due,
    )


def run(record) -> RunOut:
    """A run record as the wire shape.

    ``thread_id``, ``cancel_requested`` and ``usage_recorded`` are deliberately absent:
    they are how the worker and the sweeper talk to each other, and a client that could
    see a thread id could resume somebody's paid run.
    """
    return RunOut(
        id=record.id,
        plant_id=record.plant_id,
        kind=record.kind,
        status=record.status,
        created_at=record.created_at,
        finished_at=record.finished_at,
        diagnosis_id=record.diagnosis_id,
        error=record.error,
    )
