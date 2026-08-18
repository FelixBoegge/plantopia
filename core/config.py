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

    db_path: Path = Path("data/plantopia.db")
    chroma_path: Path = Path("data/chroma")
    corpus_path: Path = Path("knowledge/corpus")
    upload_path: Path = Path("data/uploads")

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
