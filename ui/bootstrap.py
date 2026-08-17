"""Wire the real dependencies once per Streamlit session.

The construction itself lives in ``agent/wiring.py``, which knows nothing about
Streamlit; this module is the caching layer over it. ``st.cache_resource`` is what
turns "runs on every rerun" into "runs once per process", and every rerun
re-executes each page top to bottom.
"""

import logging
from pathlib import Path

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.diagnosis_graph import build_diagnosis_graph
from agent.wiring import build_deps, build_profile_service, now_utc, open_database
from core.config import get_settings
from data.db import connect
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from services.chat_service import ChatService
from services.diagnosis_service import DiagnosisService
from services.plant_service import PlantService
from services.profile_service import ProfileService

logger = logging.getLogger(__name__)


@st.cache_resource
def get_service() -> DiagnosisService:
    """Build the service and everything under it. Cached for the process."""
    settings = get_settings()
    profile = get_profile_service()
    deps = build_deps(profile_facts=profile.facts_for_prompt, settings=settings)

    checkpointer = SqliteSaver(connect(Path(str(settings.db_path) + ".checkpoints")))
    graph = build_diagnosis_graph(deps, checkpointer)

    return DiagnosisService(deps, graph, upload_dir=settings.upload_path, profile=profile)


@st.cache_resource
def get_plant_service() -> PlantService:
    """Build the plant-profile service. Cached for the process.

    Opens its own connection to the same database file ``get_service`` uses.
    ``data.db.transaction``'s write lock is module-level, not per-connection, so
    writes through either connection still serialise correctly against each other
    (see ``data/db.py``'s docstring).
    """
    conn = open_database()

    return PlantService(
        plants=PlantRepository(conn),
        observations=ObservationRepository(conn),
        diagnoses=DiagnosisRepository(conn),
        roadmap=RoadmapRepository(conn),
        feedback=FeedbackRepository(conn),
        now=now_utc,
    )


@st.cache_resource
def get_profile_service() -> ProfileService:
    """Build the profile service. Cached for the process.

    Opens its own connection to the same database file, like its siblings; the
    module-level write lock in ``data/db.py`` serialises writes across them.
    """
    return build_profile_service()


@st.cache_resource
def get_chat_service() -> ChatService:
    """Build the chat service. Cached for the process.

    Reuses ``get_service()``'s ``Deps`` (same models, same repositories) rather than
    constructing a second one — the chat agent's tools are read-only wrappers over
    exactly what the diagnosis pipeline already has.

    The ReAct loop gets its own ``SqliteSaver`` file rather than sharing the
    diagnosis graph's. Thread ids alone would keep the two apart (``chat:{id}`` vs
    the wizard's uuid/``recheck-…`` threads), but the diagnosis checkpoint file grows
    by ~100 MB per run (M15) because graph state carries whole images, and a chat
    transcript has no business sharing a file that gets pruned on that schedule.
    """
    settings = get_settings()
    conn = open_database(settings)

    service = get_service()
    return ChatService(
        deps=service._deps,
        messages=MessageRepository(conn),
        checkpointer=SqliteSaver(connect(Path(str(settings.db_path) + ".chat-checkpoints"))),
        now=now_utc,
        profile=get_profile_service(),
    )
