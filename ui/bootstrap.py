"""Wire the real dependencies once per Streamlit session.

The construction itself lives in ``agent/wiring.py``, which knows nothing about
Streamlit; this module is the caching layer over it. ``st.cache_resource`` is what
turns "runs on every rerun" into "runs once per process", and every rerun
re-executes each page top to bottom.
"""

import logging

import streamlit as st

from agent.checkpoints import build_checkpointer, checkpointer_url
from agent.diagnosis_graph import build_diagnosis_graph
from agent.wiring import build_deps, build_profile_service, default_owner_id, now_utc, open_session
from core.blobs import PostgresBlobStore
from core.config import get_settings
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

    graph = build_diagnosis_graph(deps, build_checkpointer(checkpointer_url(settings)))

    return DiagnosisService(deps, graph, profile=profile)


@st.cache_resource
def get_plant_service() -> PlantService:
    """Build the plant-profile service. Cached for the process.

    Opens its own session on the shared pool. Sessions are cheap and independent —
    unlike the SQLite connections this replaced, they need no cross-connection locking,
    because Postgres resolves concurrent writers itself.
    """
    session = open_session()

    return PlantService(
        user_id=default_owner_id(session),
        plants=PlantRepository(session),
        observations=ObservationRepository(session),
        diagnoses=DiagnosisRepository(session),
        roadmap=RoadmapRepository(session),
        feedback=FeedbackRepository(session),
        blobs=PostgresBlobStore(session),
        now=now_utc,
    )


@st.cache_resource
def get_profile_service() -> ProfileService:
    """Build the profile service. Cached for the process.

    Opens its own session on the shared pool, like its siblings.
    """
    return build_profile_service()


@st.cache_resource
def get_chat_service() -> ChatService:
    """Build the chat service. Cached for the process.

    Reuses ``get_service()``'s ``Deps`` (same models, same repositories) rather than
    constructing a second one — the chat agent's tools are read-only wrappers over
    exactly what the diagnosis pipeline already has.

    Shares the diagnosis graph's checkpointer now. The two had separate SQLite files
    because the diagnosis one grew by ~100 MB per run (M15) and a chat transcript had no
    business sharing a file pruned on that schedule. State carries blob keys rather than
    images, so that reason is gone, and thread ids keep the two apart by construction.
    """
    settings = get_settings()
    session = open_session(settings)

    service = get_service()
    return ChatService(
        deps=service._deps,
        messages=MessageRepository(session),
        checkpointer=build_checkpointer(checkpointer_url(settings)),
        now=now_utc,
        profile=get_profile_service(),
    )


@st.cache_resource
def get_blob_store() -> PostgresBlobStore:
    """The photograph store, for pages that render one."""
    return PostgresBlobStore(open_session())
