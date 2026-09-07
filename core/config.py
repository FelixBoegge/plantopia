"""Application configuration, loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every tunable value in the application. Nothing reads os.environ directly."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLANTOPIA_",
        extra="ignore",
        case_sensitive=False,
    )

    # OpenRouter. Every model call in the application goes through it.
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Where the web client is served. Every link in an email is built from this, so a
    # wrong value is a link nobody can follow and nobody can be told about. The default is
    # Vite's development port; a deployment sets it to the real address.
    app_url: str = "http://localhost:5173"
    app_title: str = "Plantopia"

    # Three model tiers. OpenRouter makes swapping trivial, so the pipeline uses the
    # cheapest model that can do each job.
    #
    # These defaults are the strongest combination verified reachable and tool-calling
    # on a restricted (college-issued) OpenRouter key. Many stronger models —
    # anthropic/claude-sonnet-4.5, openai/gpt-4.1, google/gemini-2.5-pro — return
    # "No endpoints available matching your guardrail restrictions and data policy"
    # on such accounts, so they are documented as overrides in .env.example rather
    # than chosen here. Re-probe before assuming any slug still resolves.
    gate_model: str = "google/gemini-2.5-flash-lite"
    vision_model: str = "google/gemini-2.5-flash"
    reasoning_model: str = "openai/gpt-4o"

    # Retrieval embeddings, via OpenRouter's /embeddings endpoint. The corpus vectors in
    # `corpus_chunks` come from this model, and the column is fixed at its width — so
    # changing it means an Alembic migration and re-running `knowledge.ingest_corpus`.
    embedding_model: str = "openai/text-embedding-3-small"

    tavily_api_key: str | None = None

    # Pl@ntNet's identification API. Optional in exactly the way tavily_api_key is: absent,
    # the second identification simply does not happen and the diagnosis proceeds on the
    # vision model's guess alone. That is not a degraded mode bolted on — it is what this
    # project did before the service existed, and it stays the path a deployment without a
    # key takes.
    plantnet_api_key: str | None = None

    # Reverse geocoding, for turning a position read from a photograph into a place name a
    # person recognises. Keyless — OpenStreetMap's own service — so this works on a fresh
    # clone rather than being dark until somebody registers.
    #
    # Both are configurable because the terms make them matter: the user agent must identify
    # the application and should carry a real contact address, and a deployment doing more
    # than the shared service's one-request-a-second should point at its own instance.
    geocoding_url: str = "https://nominatim.openstreetmap.org/reverse"
    geocoding_user_agent: str = (
        "Plantopia/1.0 (plant health assistant; https://github.com/plantopia)"
    )

    # LangSmith tracing. Optional in exactly the way tavily_api_key is: absent, the
    # application runs unchanged and tracing is simply off (spec §2.4). Because
    # LangChain's tracer is itself a callback, a key is all the wiring there is —
    # every node, tool call, retrieval and model call is traced automatically.
    langsmith_api_key: str | None = None
    langsmith_project: str = "plantopia"

    # LangSmith API keys are region-scoped: a key from an EU workspace 403s against
    # the default US host. `None` means "let the SDK use its own default" rather than
    # hardcoding the US URL, so a future SDK default change is inherited for free —
    # only set this when the workspace is actually on a non-default region/host.
    langsmith_endpoint: str | None = None

    # One Postgres holds domain records, the corpus vectors and both graph
    # checkpointers. The driver is named explicitly because SQLAlchemy's bare
    # ``postgresql://`` still resolves to psycopg2, which is not installed —
    # the failure is an obscure ImportError rather than anything that names the URL.
    # The default matches docker-compose.yml so a fresh clone needs no .env entry —
    # including its port, which is 5433 because a machine with PostgreSQL already
    # installed has a service on 5432 that the container would otherwise contend with.
    database_url: str = "postgresql+psycopg://plantopia:plantopia@localhost:5433/plantopia"

    corpus_path: Path = Path("knowledge/corpus")

    # Where the evaluation harness writes its results, and where the API reads the newest
    # one from. One setting rather than a constant in each, so the two cannot drift into
    # reading and writing different directories.
    eval_results_path: Path = Path("eval/results")

    # Whether an ordinary member may read those results. **Temporary, and off by default.**
    #
    # The evaluation page is admin-only because harness numbers are internal. For the
    # capstone review it has to be reachable by a reviewer who registers an ordinary
    # account, and that is a property of this deployment rather than of the rule — so it
    # lives here instead of in ``identity/roles.may_read_evaluations``. Written as a code
    # change it would have to be remembered and reverted, and an opened resource is the
    # worst thing to leave to memory; as configuration, a deployment that says nothing
    # inherits the closed state. ``docs/deployment-readiness.md`` carries the re-lock.
    #
    # An unknown role is still refused either way. This widens the rule to members, not to
    # everybody.
    evaluation_open_to_members: bool = False

    # The HTTP interface. Every route is served beneath the prefix, so a later
    # incompatible version can exist alongside this one rather than replacing it under a
    # running client.
    api_prefix: str = "/api/v1"

    # Origins permitted to make cross-origin requests, comma-separated. Empty by default
    # and deliberately never "*": a permissive default is the kind of thing that ships
    # because nobody had a reason to tighten it yet.
    cors_origins: str = ""

    # Signs access tokens. **No default, deliberately.** A generated one would work
    # perfectly in development and log everybody out at random in production, because a
    # process restart would invalidate every token issued before it — a failure that
    # first appears as users complaining, long after the cause.
    #
    # At least 32 characters, which is RFC 7518's floor for HMAC-SHA256: a shorter key
    # weakens the signature, and PyJWT warns about it rather than refusing, so a short
    # one would otherwise ship behind a log line nobody reads.
    jwt_secret: str = Field(min_length=32)

    # Short, because an access token cannot be revoked: it is believed until it expires,
    # so its lifetime is the window a stolen one is useful for.
    access_token_minutes: int = Field(default=15, ge=1, le=60)

    # Long, because this one *can* be revoked — it is stored, rotated and checked.
    refresh_token_days: int = Field(default=30, ge=1, le=365)

    verification_token_hours: int = Field(default=24, ge=1, le=168)
    reset_token_hours: int = Field(default=1, ge=1, le=24)

    # How much the application's own loggers say. Uvicorn configures its own handlers and
    # leaves everybody else at WARNING, which silently swallows the console mailer — the
    # thing a developer registering an account is supposed to read the verification link
    # out of.
    log_level: str = "INFO"

    # Whether the refresh cookie is marked Secure. True everywhere it matters; False is
    # what lets a browser keep the cookie when the frontend is served over plain http on
    # localhost, which is the only situation where turning it off is defensible.
    secure_cookies: bool = True

    minimum_password_length: int = Field(default=12, ge=8, le=128)

    # The privacy notice version a registration agrees to. Stored per account, so
    # changing this does not rewrite what anybody previously consented to.
    consent_version: str = "2026-08-25"

    # Transactional email. Absent a key, messages are written to the log instead of sent,
    # which is what development and tests use.
    resend_api_key: str | None = None
    mail_from: str = "Plantopia <onboarding@resend.dev>"

    # How many diagnoses one account may run per calendar month, and what everybody
    # together may spend in a day. A diagnosis costs roughly five cents; open
    # registration without either of these is an unmetered bill with a signup form.
    monthly_run_allowance: int = Field(default=20, ge=1)

    # Per-tier overrides of the allowance above, so introducing a paid tier is a
    # configuration change rather than a code one. A tier absent from here gets the
    # default: an unrecognised tier should be an ordinary account, not a locked one.
    tier_allowances: dict[str, int] = Field(default_factory=dict)
    daily_spend_cap_usd: float = Field(default=5.0, gt=0)

    # Per-source limits on the three unauthenticated endpoints that are cheap to hammer.
    auth_rate_limit: int = Field(default=10, ge=1)
    auth_rate_window_seconds: int = Field(default=300, ge=1)

    # Background runs. The pool is small because the work is IO-bound waiting on a
    # provider, not CPU — more threads buy queue depth, not throughput, and each one
    # holds a database connection while it works.
    run_pool_size: int = Field(default=4, ge=1, le=64)

    # What the queue will hold before a run is refused at the door. Unbounded, a burst
    # becomes a pile of runs that each take minutes and each hold a checkpoint; refusing
    # is the only answer that tells somebody to come back shortly.
    run_queue_limit: int = Field(default=32, ge=1)

    # Two ceilings, because waiting for a person is not the same as being stuck. A run
    # still `running` past the first is a process that died. One `awaiting_answers` past
    # the second is somebody who closed the tab. A single number would either reap live
    # conversations or leave dead runs for hours.
    run_working_ceiling_minutes: int = Field(default=10, ge=1)
    run_answering_ceiling_minutes: int = Field(default=60, ge=1)

    # How often an idle event stream says something. A run can spend a minute inside one
    # model call, and intermediaries close connections that look idle.
    run_keepalive_seconds: int = Field(default=15, ge=1, le=300)

    # Whether this process sweeps abandoned runs. One process should; several would each
    # sweep, which is harmless but wasteful, and is the open question the deployment change
    # settles. Off in tests, where runs are driven directly and a background loop would only
    # add timing.
    run_sweeper_enabled: bool = True
    run_sweeper_interval_seconds: int = Field(default=60, ge=5)

    retrieval_score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    species_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    diagnosis_confidence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)

    # How many questions the *agent* may add. The four fixed fields — watering, drainage,
    # where the plant is, when the photograph was taken — sit outside this: without a place
    # and a date there is no weather at all, which is a different thing from a shorter form.
    #
    # Four rather than two, because what the agent asks about is now the plant's recent
    # history, and one question rarely covers it: repotted, fed, moved and treated are four
    # separate facts, any of which explains symptoms that otherwise read as disease.
    max_clarifying_questions: int = Field(default=4, ge=1, le=8)

    # How old a photograph may be before the owner is warned and the diagnosis is told.
    #
    # A plant changes. A photograph three weeks old shows a plant that no longer exists, and
    # a diagnosis of it is a diagnosis of the past presented as advice about the present.
    #
    # Seven days because that is roughly the period over which the disorders in this corpus
    # become visibly different — a week of overwatering shows, a week of nitrogen deficiency
    # shows — and because it is a period a person can hold in their head. Configuration
    # rather than a constant so that a deployment with a slower corpus can move it.
    stale_photograph_days: int = Field(default=7, ge=1, le=365)
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, gt=0)

    # **The long-edge cap applied to a stored photograph.** 1568 is the point beyond which
    # the major vision models downscale server side anyway, so pixels above it are paid for
    # and then discarded. A setting rather than a constant because every other limit
    # governing an upload is one, and a reviewer changing one should find them together.
    max_image_edge_px: int = Field(default=1568, gt=0)

    # How large a data export may grow before it is refused rather than built.
    #
    # The archive is assembled in memory, so this is a guard on the process rather than on
    # the person: an account with hundreds of photographs would otherwise be a request that
    # takes the server down instead of one that fails. 256 MB is roughly thirty full-size
    # uploads, which is more than any account here holds and far less than the machine has.
    max_export_bytes: int = Field(default=256 * 1024 * 1024, gt=0)

    # When a chat conversation stops replaying its old tool output to the model.
    #
    # Measured on this repository's own data: a web-search result is about 1,315 tokens, a
    # weather block about 250, a knowledge lookup about 295 — against roughly 200 for
    # everything a person and the agent actually said in the same turn. Tool output is the
    # bulk by six to one, and a search from twenty turns ago is not what the current
    # question is about.
    #
    # Well below any model's context window, deliberately. Waiting until the window was
    # nearly full would mean paying for every one of those tokens on every turn until it
    # fired, and the point is to avoid the bill rather than to avoid an error.
    chat_clear_tools_after_tokens: int = Field(default=8_000, gt=0)

    # How many recent tool results survive that clearing. Small, because the value is
    # concentrated in the latest: the agent is answering the question in front of it.
    chat_keep_recent_tool_results: int = Field(default=3, ge=1, le=20)

    # When the conversation *itself* is condensed — the backstop, not the working part.
    # At roughly 200 tokens a turn this takes hundreds of exchanges, and by then clearing
    # tool output has long since done the useful work. It exists because without it there
    # is still no bound, and unboundedness is the thing being fixed.
    chat_summarise_after_tokens: int = Field(default=32_000, gt=0)

    # How many recent exchanges stay word for word when that happens. An agent that
    # summarised what was just said would be answering a paraphrase of the question.
    chat_keep_recent_messages: int = Field(default=20, ge=2, le=100)
    max_images_per_observation: int = Field(default=4, ge=1, le=10)

    default_temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    # Above the OpenAI client's default of 2. Connections to OpenRouter drop under
    # sustained concurrency, and a probe of the Ragas judge caught the client
    # retrying three times and then surfacing APIConnectionError — which cost that
    # evaluation most of its cells, and would cost a real diagnosis its result.
    model_max_retries: int = Field(default=6, ge=0, le=20)

    @property
    def allowed_origins(self) -> list[str]:
        """``cors_origins`` split into a list, with blanks dropped."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
