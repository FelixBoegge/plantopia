"""The dependency container injected into every graph node.

Nodes never construct a model, open a database connection, or call ``datetime.now``.
Everything arrives here, which is what makes the pipeline testable offline.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from langchain_core.language_models import BaseChatModel

from agent.schemas import CareProfile, Passage, WeatherSummary
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

    # Three model tiers, cheapest job to hardest. See core/llm.py for why.
    gate_model: BaseChatModel  # guard_input, quality_check
    vision_model: BaseChatModel  # identify_plant, assess_symptoms
    chat_model: BaseChatModel  # question selection, diagnose, build_roadmap

    retriever: Retriever

    plants: PlantRepository
    observations: ObservationRepository
    diagnoses: DiagnosisRepository
    roadmap: RoadmapRepository

    weather: Callable[[str, int], WeatherSummary | None]
    web_search: Callable[[str], list[Passage]]
    care_profile: Callable[[str], CareProfile | None]

    now: Callable[[], datetime]
