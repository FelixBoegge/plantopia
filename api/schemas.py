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


class LoginIn(BaseModel):
    """Credentials. Neither field is echoed anywhere."""

    email: EmailStr
    password: str


class SessionOut(BaseModel):
    """What a sign-in or a refresh hands back.

    The refresh token is deliberately absent: it travels as an httpOnly cookie, and putting
    it here as well would hand it to any script that can read the response.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class ResetRequestIn(BaseModel):
    """An address to send a reset link to, whether or not it has an account."""

    email: EmailStr


class ResetConfirmIn(BaseModel):
    """A reset link and the password to set with it."""

    token: str = Field(min_length=1)
    password: str


class RunOut(BaseModel):
    """A run as a client sees it.

    ``status`` is the contract. A client branches on it and never infers one from silence,
    which is why every field that could be mistaken for a status — a finish time, a
    diagnosis — is optional and none of them is the source of truth.
    """

    id: UUID
    plant_id: UUID | None
    kind: str
    status: Literal["queued", "running", "awaiting_answers", "completed", "failed", "cancelled"]
    created_at: datetime
    finished_at: datetime | None
    diagnosis_id: UUID | None
    error: str | None


class AnswersIn(BaseModel):
    """The answers a paused run asked for, keyed by the question keys it sent."""

    answers: dict[str, str]


class AccountOut(BaseModel):
    """A person's own account.

    Carries the allowance alongside the identity because a screen needs both to draw once,
    and because being told "you have used your twenty runs" by a failed diagnosis is being
    told too late.
    """

    id: UUID
    # ``str``, not ``EmailStr``. Validation belongs at the door: this address was checked
    # when the account was registered, and re-checking it on the way out means a stored
    # value the validator dislikes — a legacy row, a stricter version of the library —
    # makes somebody's own account page permanently unloadable to them.
    email: str
    created_at: datetime
    tier: str
    role: str
    consent_version: str
    consent_at: datetime
    runs_used: int
    runs_allowed: int
    allowance_resets_at: datetime


class EvaluationOut(BaseModel):
    """The newest harness result, or the plain statement that there is none.

    ``results`` is passed through unshaped. It is a report somebody reads, not an interface
    anything branches on, and typing it here would be a second copy of the harness's own
    format to keep in step.
    """

    generated_at: str | None
    results: dict | None


class DiagnosisDetailOut(BaseModel):
    """One diagnosis with the plan it produced.

    The two are read together on every screen that shows either, so they travel together
    rather than as two requests a client has to sequence.
    """

    diagnosis: DiagnosisOut
    roadmap_steps: list[RoadmapStepOut]
