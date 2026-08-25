"""What the API sends and accepts.

Written out rather than inferred from the repository records. Those are storage shapes:
returning them directly would make every column a public field, so dropping one becomes a
breaking change for clients, and a column added for an internal reason gets published by
accident. These say what a client may rely on, and nothing else.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class PlantOut(BaseModel):
    id: UUID
    name: str
    species: str | None
    species_confidence: float | None
    location_kind: Literal["indoor", "outdoor"]
    location_text: str | None
    photo_ref: str | None
    created_at: datetime


class CandidateOut(BaseModel):
    disorder_id: str
    name: str
    probability: float
    severity: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    distinguishing_test: str


class DiagnosisOut(BaseModel):
    id: UUID
    plant_id: UUID
    observation_id: UUID
    is_healthy: bool
    reasoning: str
    candidates: list[CandidateOut]
    created_at: datetime
    cost_usd: float | None


class ObservationOut(BaseModel):
    id: UUID
    plant_id: UUID
    kind: Literal["initial", "recheck"]
    photo_refs: list[str]
    user_notes: str | None
    created_at: datetime


class RoadmapStepOut(BaseModel):
    id: UUID
    diagnosis_id: UUID
    ordinal: int
    action: str
    rationale: str
    success_signal: str
    tier: int
    due_date: datetime
    status: Literal["pending", "done", "skipped"]
    completed_at: datetime | None


class PlantSummaryOut(BaseModel):
    """One row of the plant list."""

    plant: PlantOut
    latest_diagnosis: DiagnosisOut | None
    pending_step_count: int


class PlantDetailOut(BaseModel):
    """Everything a plant page renders."""

    plant: PlantOut
    observations: list[ObservationOut]
    diagnoses: list[DiagnosisOut]
    roadmap_steps: list[RoadmapStepOut]
    feedback_due: bool


class RenamePlantIn(BaseModel):
    name: str = Field(min_length=1)


class MessageOut(BaseModel):
    id: UUID
    plant_id: UUID
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[dict] | None
    created_at: datetime


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1)


class ChatReplyOut(BaseModel):
    """One exchange.

    ``escalated`` is the agent saying the described symptoms differ enough from the last
    diagnosis to warrant a fresh look. It is the agent's own judgement, surfaced rather
    than acted on: nothing here starts a diagnosis.
    """

    reply: str
    escalated: bool


class MarkStepIn(BaseModel):
    status: Literal["pending", "done", "skipped"]


class FeedbackIn(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    did_it_help: Literal["yes", "no", "unclear", "too_early"] | None = None
    free_text: str | None = None


class ProfileFactOut(BaseModel):
    fact: str
    source: Literal["inferred", "stated"]
    confidence: float
    first_seen: datetime
    last_confirmed: datetime


class ForgetFactIn(BaseModel):
    fact: str = Field(min_length=1)


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ready", "not ready"]
    database: bool


class RegisterIn(BaseModel):
    """What creating an account needs.

    The password has no upper bound worth enforcing here beyond argon2's own: a length
    limit on a hashed secret protects nothing except against somebody posting a megabyte,
    which the body-size limit already covers.
    """

    email: EmailStr
    password: str
    accepted_privacy_notice: bool = Field(
        description="Whether the privacy notice was agreed to. Registration is refused without it."
    )


class VerifyIn(BaseModel):
    """The token from a verification link."""

    token: str = Field(min_length=1)
