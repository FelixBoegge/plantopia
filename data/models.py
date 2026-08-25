"""The database schema, as typed models.

Replaces ``data/schema.sql``. The shape is deliberately the same one that file
described — this change moves where records live and who may read them, not what a
plant history is made of. Three things do differ, each for a reason:

**Identifiers are UUIDv7** (``core.ids``), not autoincrementing integers, so a record
identifier discloses neither how many records exist nor what the next one will be.

**Times are ``timestamptz``**, not ISO strings parsed by hand on the way out. ``M3``
recorded ``PARSE_DECLTYPES`` as a line that read like a guarantee and did nothing,
because every temporal column was declared TEXT; the driver can now do what that line
claimed.

**Ownership is a column**, on the three tables that have an owner directly. The rest
reach one through their parent, and the cascades that already existed carry the
deletion down. This is what makes ``UNIQUE(fact)`` on the profile wrong — two people
may perfectly well both tend to overwater — so it becomes ``UNIQUE(user_id, fact)``.
"""

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.ids import new_id

# text-embedding-3-small. Changing this means re-embedding the corpus: vectors from
# two different models are not comparable, and pgvector will happily store the wrong
# ones alongside the right ones.
EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    """Declarative base. Alembic autogenerates against ``Base.metadata``."""


def _pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=new_id)


def _owner() -> Mapped[UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _plant() -> Mapped[UUID]:
    return mapped_column(ForeignKey("plants.id", ondelete="CASCADE"), index=True)


def _when(**kw: object) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)  # type: ignore[arg-type]


class User(Base):
    """A person with an account.

    ``email`` is stored lowercased and is the identity: addresses are compared
    case-insensitively in practice, and storing what somebody typed would let the same
    person register twice.

    ``password_hash`` is argon2id and nothing else. There is no column, log or response
    anywhere that carries a password in a recoverable form.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _when()

    # Null until the address is proven. An unverified account cannot sign in, which is
    # what stops somebody registering an address they do not control.
    verified_at: Mapped[datetime | None] = _when(nullable=True)

    # Which version of the privacy notice was agreed, and when. Consent that cannot be
    # evidenced afterwards is not consent, and registration is the only moment to capture
    # it.
    consent_version: Mapped[str] = mapped_column(String(32))
    consent_at: Mapped[datetime] = _when()

    # One value today. Quotas read it, so a second tier is a row change rather than a
    # code change.
    tier: Mapped[str] = mapped_column(String(32), default="free")


class RefreshToken(Base):
    """One issued refresh token.

    Stored as a hash: a database dump must not be a set of working sessions.

    ``family_id`` is what makes reuse detection possible. Every token descended from one
    sign-in shares it, so discovering a token used twice — which means two parties hold
    it — can invalidate all of them rather than refusing one request while the thief's
    newer token keeps working.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("idx_refresh_family", "family_id"),)

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    family_id: Mapped[UUID] = mapped_column()
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    issued_at: Mapped[datetime] = _when()
    expires_at: Mapped[datetime] = _when()

    # Set when the token is rotated. Presenting a token that carries this is the signal
    # that something has gone wrong.
    used_at: Mapped[datetime | None] = _when(nullable=True)

    # Set when the family is invalidated, by sign-out, by a password reset, or by reuse.
    revoked_at: Mapped[datetime | None] = _when(nullable=True)


class EmailToken(Base):
    """A single-use link sent to an address: verification, or password reset.

    Hashed like a refresh token, and for the same reason. A stolen database should not
    yield a working password-reset link for every account in it.
    """

    __tablename__ = "email_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('verify', 'reset')", name="ck_email_tokens_purpose"),
    )

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    purpose: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = _when()
    expires_at: Mapped[datetime] = _when()
    used_at: Mapped[datetime | None] = _when(nullable=True)


class UsageEvent(Base):
    """What one run cost, attributed to whoever started it.

    Per *run*, not per diagnosis. A run that spends on vision and reasoning and then
    fails to produce a differential is recorded here all the same — a quota that cannot
    see failed runs is one somebody can exhaust the budget through by failing.

    ``cost_usd`` is null when the provider reported none, which is deliberately different
    from zero: an unmeasured run must not be readable as a free one.
    """

    __tablename__ = "usage_events"
    __table_args__ = (Index("idx_usage_user_time", "user_id", "occurred_at"),)

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    kind: Mapped[str] = mapped_column(String(32))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    succeeded: Mapped[bool] = mapped_column(Boolean)
    occurred_at: Mapped[datetime] = _when()


class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = (
        CheckConstraint("location_kind IN ('indoor', 'outdoor')", name="ck_plants_location_kind"),
    )

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    name: Mapped[str] = mapped_column(Text)
    species: Mapped[str | None] = mapped_column(Text)
    species_confidence: Mapped[float | None] = mapped_column(Float)
    location_kind: Mapped[str] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    acquired_at: Mapped[datetime | None] = _when(nullable=True)
    photo_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _when()


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint("kind IN ('initial', 'recheck')", name="ck_observations_kind"),
    )

    id: Mapped[UUID] = _pk()
    plant_id: Mapped[UUID] = _plant()
    kind: Mapped[str] = mapped_column(Text)
    photo_refs: Mapped[str] = mapped_column(Text)
    user_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _when()


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[UUID] = _pk()
    observation_id: Mapped[UUID] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"))
    plant_id: Mapped[UUID] = _plant()
    differential_json: Mapped[str] = mapped_column(Text)
    primary_candidate: Mapped[str | None] = mapped_column(Text)
    primary_confidence: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(Text)
    contagion_json: Mapped[str | None] = mapped_column(Text)
    retrieved_refs_json: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    token_usage_json: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _when()


class RoadmapStep(Base):
    __tablename__ = "roadmap_steps"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'skipped')", name="ck_roadmap_steps_status"),
        Index("idx_roadmap_status", "status", "due_date"),
    )

    id: Mapped[UUID] = _pk()
    diagnosis_id: Mapped[UUID] = mapped_column(ForeignKey("diagnoses.id", ondelete="CASCADE"))
    plant_id: Mapped[UUID] = _plant()
    ordinal: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    success_signal: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[datetime] = _when()
    status: Mapped[str] = mapped_column(Text, default="pending")
    completed_at: Mapped[datetime | None] = _when(nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        CheckConstraint(
            "did_it_help IN ('yes', 'no', 'unclear', 'too_early')", name="ck_feedback_did_it_help"
        ),
    )

    id: Mapped[UUID] = _pk()
    diagnosis_id: Mapped[UUID] = mapped_column(ForeignKey("diagnoses.id", ondelete="CASCADE"))
    rating: Mapped[int | None] = mapped_column(Integer)
    did_it_help: Mapped[str | None] = mapped_column(Text)
    free_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _when()


class ProfileFact(Base):
    """A durable fact about the owner, not about a plant.

    ``UNIQUE(user_id, fact)`` rather than the ``UNIQUE(fact)`` the SQLite schema
    carried: the old constraint was correct for exactly one user and silently wrong for
    two, since it would have made the second person to tend to overwater a conflict.
    """

    __tablename__ = "user_profile"
    __table_args__ = (
        UniqueConstraint("user_id", "fact", name="uq_user_profile_owner_fact"),
        CheckConstraint("source IN ('inferred', 'stated')", name="ck_user_profile_source"),
    )

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    fact: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    first_seen: Mapped[datetime] = _when()
    last_confirmed: Mapped[datetime] = _when()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'tool')", name="ck_messages_role"),
        Index("idx_messages_plant", "plant_id", "created_at"),
    )

    id: Mapped[UUID] = _pk()
    plant_id: Mapped[UUID] = _plant()
    user_id: Mapped[UUID] = _owner()
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    tool_calls_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _when()


class ProfileCursor(Base):
    """How far profile extraction has read each plant's chat thread.

    Keyed by plant because each thread advances independently, and kept out of
    ``messages`` so a profile concern stays out of a table about conversation.
    """

    __tablename__ = "profile_cursors"

    plant_id: Mapped[UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), primary_key=True
    )
    last_message_id: Mapped[UUID] = mapped_column()


class Blob(Base):
    """An uploaded photograph.

    Owned directly rather than through a plant: an upload exists before the plant it
    documents does — the wizard stores photographs, then identifies the species, then
    creates the plant — so there is no parent to reach an owner through at that point.
    """

    __tablename__ = "blobs"

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    content_type: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class CorpusChunk(Base):
    """One section of one disorder document, with its embedding.

    Reference data, not a record: the corpus is the same for everyone, so this table
    has no owner and no cascade. It is keyed by ``(doc_id, section)`` rather than by a
    generated identifier because that pair *is* the identity — it is what
    ``sections_for`` looks a passage up by, and what the Chroma ids it replaces encoded
    as ``doc_id::section``.

    **No index on ``embedding``.** 301 rows is a sub-millisecond sequential scan, and
    an approximate index (HNSW) can reorder results by construction — which would make
    the parity gate unable to attribute a difference to the new SQL rather than to the
    index. Add one if the corpus ever grows by an order of magnitude.
    """

    __tablename__ = "corpus_chunks"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    section: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    transmissible: Mapped[bool] = mapped_column(Boolean)
    severity: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
