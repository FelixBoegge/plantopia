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
    __table_args__ = (CheckConstraint("role IN ('member', 'admin')", name="ck_users_role"),)

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

    # What this account may reach, as opposed to what it may spend. Tenancy decides
    # everything a person owns; a role decides access to the one thing nobody owns — the
    # evaluation results. Two values and a default, so every account that already exists is
    # unchanged and nothing needs a permission system to describe it.
    role: Mapped[str] = mapped_column(String(32), default="member", server_default="member")


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

    # When the photographs said they were taken, as distinct from when they were uploaded.
    # `created_at` below is the upload; this is the observation. They differ whenever
    # somebody photographs a plant and gets round to it later, and the difference decides
    # which three weeks of weather the diagnosis is read against.
    #
    # Null means no photograph declared one, which is most of them and is not a failure.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Where, to about eleven kilometres. Deliberately no finer: `core/metadata.py` coarsens
    # on arrival and the precise fix is never handed to anything that could write it here.
    # A database that never held somebody's address cannot leak one.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # The weather the diagnosis was made against, day by day, as a serialised
    # `WeatherSummary`.
    #
    # One column rather than a table of weather rows: nothing queries across observations by
    # weather, the series is always read whole and always belongs to exactly one
    # observation, and a table would be a join to reconstruct a list that was always a list.
    #
    # Stored because a diagnosis's evidence should be recoverable — the argument
    # `species_method` already made. Null means no weather was recorded, which is true of
    # every observation made before this column existed and of every indoor plant. That is a
    # different fact from an empty window, and the two are kept distinguishable.
    weather_json: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = _when()


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[UUID] = _pk()
    observation_id: Mapped[UUID] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"))
    plant_id: Mapped[UUID] = _plant()
    differential_json: Mapped[str] = mapped_column(Text)

    # Where the species came from, and whether a person agreed to it.
    #
    # A wrong diagnosis has two causes that look identical afterwards: bad reasoning about
    # the right plant, or good reasoning about the wrong one. These two columns are what
    # separates them.
    #
    # `species_method` is nullable and means unknown when it is null — which is the honest
    # answer for every row written before this existed, and for a run whose identification
    # failed outright. A backfill would have to invent one.
    species_method: Mapped[str | None] = mapped_column(Text)
    species_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # How a re-check compared with the diagnosis before it. Null on a first diagnosis, which
    # has nothing to compare against, and on any re-check made before this was recorded.
    progress_verdict: Mapped[str | None] = mapped_column(Text)

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


class SpeciesCareProfile(Base):
    """Baseline care requirements for one species, researched rather than hand-written.

    Reference data, not a record — the same argument `CorpusChunk` makes. What *Monstera
    deliciosa* wants is the same fact for everybody, so this table has **no owner and no
    cascade**: scoping it per person would mean researching the same species again for every
    account that photographs one, which is the cost the cache exists to avoid.

    The consequence, stated rather than buried: one owner's run writes a row other owners'
    runs read. Nothing personal crosses that boundary — a species name and public care
    guidance — but a bad profile would be bad for everybody, which is why the refusal rule
    and the untrusted fencing around what produced it are requirements rather than niceties.

    Keyed by the normalised species name because that *is* the identity, in the same way
    ``(doc_id, section)`` is `CorpusChunk`'s. Normalised on the way in so that "Monstera
    Deliciosa", "monstera deliciosa" and " monstera deliciosa " are one row rather than three.

    Only ever holds researched profiles. The hand-written tier lives in
    ``tools/care_profiles.py`` and always wins, so a row here can never shadow one.
    """

    __tablename__ = "species_care_profiles"

    species_key: Mapped[str] = mapped_column(Text, primary_key=True)

    # The species as it should be shown, which is not the key: the key is lowercased for
    # matching and nobody wants to read "ocimum africanum" in a care note.
    species: Mapped[str] = mapped_column(Text)
    light: Mapped[str] = mapped_column(Text)
    water: Mapped[str] = mapped_column(Text)
    temperature_min_c: Mapped[int] = mapped_column(Integer)
    temperature_max_c: Mapped[int] = mapped_column(Integer)
    humidity: Mapped[str] = mapped_column(Text)

    # What it was built from, as JSON. Recorded because a profile a model assembled from
    # four search results is a guess, and a guess whose provenance is gone cannot be checked
    # afterwards by anybody.
    sources_json: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = _when()


class Run(Base):
    """One execution of the agent, as a thing a client can address.

    A diagnosis takes about ninety seconds and pauses part-way to ask questions. Neither
    fits inside a request, so the work becomes a resource: the client is handed one of
    these and watches it, rather than holding a connection and hoping.

    **``status`` is the contract.** A client reads it and never infers one — silence is
    indistinguishable from a crashed worker, a slow model, and a finished run whose last
    event was lost. The constraint below is what stops an invented status becoming one.

    ``thread_id`` is the checkpoint's key, kept here because resuming after the pause has
    to find it, and because a run and its checkpoint are otherwise only related by
    convention.

    ``cancel_requested`` is a flag the worker reads between nodes rather than a status,
    because the run is still legitimately ``running`` until it notices — and a status that
    means "will stop shortly" is a status a client has to special-case.
    """

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_answers', "
            "'completed', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        CheckConstraint("kind IN ('diagnosis', 'recheck')", name="ck_runs_kind"),
        Index("idx_runs_user_time", "user_id", "created_at"),
        # What the sweeper scans: everything not yet finished, oldest first.
        Index("idx_runs_unfinished", "status", "status_changed_at"),
    )

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = _owner()
    plant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    thread_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = _when()

    # When the status last changed, which is what both ceilings measure from. Distinct
    # from ``created_at``: a run that waited an hour for answers has not been working for
    # an hour, and one clock cannot say both.
    status_changed_at: Mapped[datetime] = _when()
    finished_at: Mapped[datetime | None] = _when(nullable=True)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    # What it produced, or why it did not. ``error`` is what a client is shown, so it is
    # written already sanitised — an exception message can carry a query or a filename.
    diagnosis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("diagnoses.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Distinguishes a run the sweeper gave up on from one that failed while working, and
    # is what stops the sweeper recording usage for a run that already recorded its own.
    usage_recorded: Mapped[bool] = mapped_column(Boolean, default=False)

    # **What the passes before this one spent.** A diagnosis is driven in more than one
    # pass — the first stops at the clarifying-question interrupt — and each pass has its
    # own collector in its own worker thread. The pause between them lasts as long as
    # somebody takes to answer, which can be longer than the process lives, so carrying
    # the first pass's usage in memory would lose it to any restart. It is written here
    # instead, and the pass that finishes adds it to its own before recording the run's
    # usage once. Nothing reads this after that; it is not a second ledger.
    partial_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunEvent(Base):
    """One thing that happened during a run, in the order it happened.

    Written before it is published. Publishing first would mean a client can receive an
    event the database does not have, and a reconnect that replays a shorter history than
    the one already on screen.

    ``sequence`` is per run, not global: two concurrent runs must not interleave, and a
    global counter would make the replay query a scan across everybody's events.

    ``kind`` is a stable identifier the client may branch on. No node, function or module
    name is ever stored here — a client rendering ``identify_plant`` is a client coupled
    to the graph's internals, and renaming a node would then break the interface.
    """

    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_events_sequence"),
        Index("idx_run_events_replay", "run_id", "sequence"),
    )

    id: Mapped[UUID] = _pk()
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = _when()
