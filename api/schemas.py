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

from agent.schemas import WeatherSummary


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

    # Where the species this was reasoned from came from, and whether a person agreed to
    # it. `null` means unknown, which is what every diagnosis made before this was recorded
    # honestly says about itself.
    species_method: Literal["typed", "vision", "plantnet", "agreed"] | None = None

    # How a re-check compared with the diagnosis before it. `null` on a first diagnosis,
    # which has nothing to compare against, and on any made before this was recorded.
    progress_verdict: Literal["improving", "static", "worsening", "new_problem"] | None = None
    species_confirmed: bool = False

    # The weather this was reasoned against, day by day, or `null` where none was recorded.
    #
    # `null` covers an indoor plant, a lookup that failed, and every diagnosis made before
    # the series was kept. It is deliberately not an empty window, which would say the
    # weather was looked up and found to be nothing at all.
    weather: WeatherSummary | None = None


class ObservationOut(BaseModel):
    id: UUID
    plant_id: UUID
    kind: Literal["initial", "recheck"]
    photo_refs: list[str]
    user_notes: str | None
    created_at: datetime

    # When the photographs were taken, as distinct from `created_at`, which is when they
    # were uploaded. A history ordered by upload puts events in an order the plant never
    # experienced, so this is what a timeline dates an observation by.
    captured_at: datetime | None = None

    # Where, to about eleven kilometres. Exposed for completeness with the capture date and
    # **deliberately not drawn anywhere**: a coarse pair of coordinates is not something to
    # show somebody who already told you where their plant is. It is here because leaving
    # one of three sibling fields behind is how the next person discovers it missing.
    latitude: float | None = None
    longitude: float | None = None

    # The weather recorded against this observation. Reachable until now only through a
    # diagnosis made from it, which fails for a re-check whose run was cancelled.
    weather: WeatherSummary | None = None


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


class DeleteAccountIn(BaseModel):
    """What somebody must supply to erase their own account.

    Both fields are checked on the server. A confirmation only the browser enforces is a
    confirmation that a script does not have to type, and this is the one action in the
    system with no undo.
    """

    password: str = Field(min_length=1)

    # The literal word, typed out. Deliberately not a boolean: a checkbox is one click away
    # from an accident, and `{"confirm": true}` is what a client sends when somebody has
    # not read anything.
    confirmation: str = Field(min_length=1)


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


class ChosenSpecies(BaseModel):
    """The identification a person picked from the ones they were offered.

    Sent back rather than referred to by index, because an index means the client and the
    run have to agree on an ordering that only one of them controls — and a run resumed
    against a reordered list would silently proceed on the wrong plant.
    """

    common_name: str = Field(min_length=1)
    scientific_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class AnswersIn(BaseModel):
    """What a paused run is resumed with.

    The answers it asked for, and the species the person chose if it offered a choice.
    `species` is optional in both directions: a run that offered no choice has none to
    send, and a person who answered the questions without picking one has made no choice
    to record.
    """

    answers: dict[str, str]
    species: ChosenSpecies | None = None


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


class ActivityStepOut(BaseModel):
    """One thing the run that produced a diagnosis did.

    ``calls`` and ``duration_ms`` are optional and stay optional: steps recorded before they
    existed are read back through this same shape, and a client that required them would
    break on every run that started earlier.
    """

    sequence: int
    step: str
    description: str
    calls: str | None = None
    duration_ms: int | None = None
    occurred_at: datetime


class DiagnosisDetailOut(BaseModel):
    """One diagnosis with the plan it produced.

    The two are read together on every screen that shows either, so they travel together
    rather than as two requests a client has to sequence.
    """

    diagnosis: DiagnosisOut
    roadmap_steps: list[RoadmapStepOut]
