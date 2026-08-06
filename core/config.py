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
    # cheapest model that can do each job. Verify these slugs at openrouter.ai/models
    # before the first real run — availability and naming change.
    gate_model: str = "google/gemini-2.5-flash-lite"
    vision_model: str = "google/gemini-2.5-flash"
    reasoning_model: str = "anthropic/claude-sonnet-4.5"

    # Retrieval embeddings, also via OpenRouter's /embeddings endpoint. Multimodal:
    # text and images share one vector space, which is what makes the image-based
    # retrieval path possible (spec §10.4).
    embedding_model: str = "google/gemini-embedding-2"
    image_match_threshold: float = Field(default=0.45, ge=0.0, le=1.0)

    tavily_api_key: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
