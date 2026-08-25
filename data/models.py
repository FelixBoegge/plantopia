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

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.ids import new_id


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
    """An owner.

    Deliberately minimal. Registration, password hashing, verification and sessions
    belong to the change that introduces authentication; this table exists now because
    the foreign keys below need something to point at, and because tenancy cannot be
    tested without a second owner to be excluded.
    """

    __tablename__ = "users"

    id: Mapped[UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = _when()


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
