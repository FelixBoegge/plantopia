"""The dependency container injected into every graph node.

Nodes never construct a model, open a database connection, or call ``datetime.now``.
Everything arrives here, which is what makes the pipeline testable offline.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from langchain_core.language_models import BaseChatModel

from agent.schemas import CareProfile, Passage, WeatherSummary
from core.blobs import BlobStore
from core.config import Settings
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from knowledge.retriever import Retriever


@dataclass(frozen=True, slots=True)
class Deps:
    """Everything the graph needs from the outside world."""

    settings: Settings

    # Whose run this is. Repositories take it as their first argument, so a node cannot
    # read or write a record without saying on whose behalf — and the graph is
    # constructed per run, so there is no risk of one owner's Deps outliving their
    # request and serving the next.
    user_id: UUID

    # Three model tiers, cheapest job to hardest. See core/llm.py for why.
    gate_model: BaseChatModel  # guard_input, quality_check
    vision_model: BaseChatModel  # identify_plant, assess_symptoms
    chat_model: BaseChatModel  # question selection, diagnose, build_roadmap

    retriever: Retriever

    # Where uploaded photographs live. Reached through Deps like every other outside
    # capability, so a node cannot open storage on its own.
    blobs: BlobStore

    plants: PlantRepository
    observations: ObservationRepository
    diagnoses: DiagnosisRepository
    roadmap: RoadmapRepository

    weather: Callable[[str, int], WeatherSummary | None]
    web_search: Callable[[str], list[Passage]]
    care_profile: Callable[[str], CareProfile | None]

    # What the agent has learned about the owner, rendered for a prompt. A callable
    # rather than a value because it is read per run and the profile changes between
    # them — and because the evaluation harness binds one returning "" so an empty
    # profile can be proven to change nothing (spec §4.3).
    profile_facts: Callable[[], str]

    now: Callable[[], datetime]
