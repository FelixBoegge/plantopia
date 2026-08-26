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
    app_url: str = "http://localhost:8501"
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

    # Retrieval embeddings, via OpenRouter's /embeddings endpoint.
    embedding_model: str = "openai/text-embedding-3-small"
    image_match_threshold: float = Field(default=0.45, ge=0.0, le=1.0)

    # Whether embedding_model accepts image input. The cross-modal retrieval path
    # (spec §10.4) embeds the photograph itself and searches the same corpus, which
    # only works when text and images share one vector space.
    #
    # Off by default because no multimodal embedding model is currently reachable:
    # gemini-embedding-001 is the only candidate and is data-policy blocked on
    # restricted keys, while the OpenAI embedding models reject image input outright
    # ("OpenAI embeddings do not support image_url inputs"). Left on, every diagnosis
    # would make one doomed HTTP call per uploaded image. Turn it on together with a
    # multimodal embedding_model and the path lights up with no code change.
    multimodal_embeddings: bool = False

    tavily_api_key: str | None = None

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

    chroma_path: Path = Path("data/chroma")
    corpus_path: Path = Path("knowledge/corpus")

    # Where the evaluation harness writes its results, and where the API reads the newest
    # one from. One setting rather than a constant in each, so the two cannot drift into
    # reading and writing different directories.
    eval_results_path: Path = Path("eval/results")

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

    max_clarifying_questions: int = Field(default=4, ge=1, le=8)
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
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
