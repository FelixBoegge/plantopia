"""Wire the real dependencies once per Streamlit session."""

import logging
from pathlib import Path

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.deps import Deps
from agent.diagnosis_graph import build_diagnosis_graph
from core.config import get_settings
from core.embeddings import ImageEmbedder
from core.llm import (
    build_embeddings,
    build_gate_model,
    build_reasoning_model,
    build_vision_model,
)
from data.db import apply_schema, connect
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from knowledge.ingest import load_corpus
from knowledge.retriever import ChromaRetriever, build_vectorstore
from services.chat_service import ChatService
from services.diagnosis_service import DiagnosisService
from services.plant_service import PlantService
from services.profile_service import ProfileService
from tools.care_profiles import lookup_plant_care_profile
from tools.weather import get_local_weather
from tools.web_search import web_search_plant_info

logger = logging.getLogger(__name__)


@st.cache_resource
def get_service() -> DiagnosisService:
    """Build the service and everything under it. Cached for the process."""
    from datetime import UTC, datetime

    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(settings.db_path)
    apply_schema(conn)

    # Embeddings go through OpenRouter's /embeddings endpoint, same key as the chat
    # models. The corpus is small — roughly 300 chunks — so the whole collection
    # embeds for a fraction of a cent. Every Document gets a deterministic id
    # (doc_id::section), so re-running this on an existing persist_directory is a
    # no-op upsert rather than a re-embed — the corpus does not grow with launches.
    vectorstore = build_vectorstore(
        chunks=load_corpus(settings.corpus_path),
        embeddings=build_embeddings(),
        persist_directory=settings.chroma_path,
    )

    # The image embedder shares the collection's vector space, which is what makes
    # cross-modal retrieval work. If you change embedding_model, delete the Chroma
    # directory and re-index — vectors from two different models are not comparable.
    #
    # Wired only when the configured embedding model actually accepts images. Passing
    # it unconditionally would cost one doomed HTTP call per uploaded image on every
    # diagnosis; passing None disables the path cleanly in ChromaRetriever.
    image_embedder = (
        ImageEmbedder(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.embedding_model,
        )
        if settings.multimodal_embeddings
        else None
    )
    if image_embedder is None:
        logger.info(
            "cross-modal image retrieval disabled (multimodal_embeddings=False); "
            "diagnosis will use the text retrieval path only"
        )

    deps = Deps(
        settings=settings,
        gate_model=build_gate_model(),
        vision_model=build_vision_model(),
        chat_model=build_reasoning_model(),
        retriever=ChromaRetriever(vectorstore, image_embedder),
        plants=PlantRepository(conn),
        observations=ObservationRepository(conn),
        diagnoses=DiagnosisRepository(conn),
        roadmap=RoadmapRepository(conn),
        weather=get_local_weather,
        web_search=lambda query: web_search_plant_info(query, api_key=settings.tavily_api_key),
        care_profile=lookup_plant_care_profile,
        profile_facts=get_profile_service().facts_for_prompt,
        now=lambda: datetime.now(tz=UTC),
    )

    checkpointer = SqliteSaver(connect(Path(str(settings.db_path) + ".checkpoints")))
    graph = build_diagnosis_graph(deps, checkpointer)

    return DiagnosisService(
        deps, graph, upload_dir=settings.upload_path, profile=get_profile_service()
    )


@st.cache_resource
def get_plant_service() -> PlantService:
    """Build the plant-profile service. Cached for the process.

    Opens its own connection to the same database file ``get_service`` uses.
    ``data.db.transaction``'s write lock is module-level, not per-connection, so
    writes through either connection still serialise correctly against each other
    (see ``data/db.py``'s docstring).
    """
    from datetime import UTC, datetime

    settings = get_settings()
    conn = connect(settings.db_path)
    apply_schema(conn)

    return PlantService(
        plants=PlantRepository(conn),
        observations=ObservationRepository(conn),
        diagnoses=DiagnosisRepository(conn),
        roadmap=RoadmapRepository(conn),
        feedback=FeedbackRepository(conn),
        now=lambda: datetime.now(tz=UTC),
    )


@st.cache_resource
def get_profile_service() -> ProfileService:
    """Build the profile service. Cached for the process.

    Opens its own connection to the same database file, like its siblings; the
    module-level write lock in ``data/db.py`` serialises writes across them.
    """
    from datetime import UTC, datetime

    settings = get_settings()
    conn = connect(settings.db_path)
    apply_schema(conn)

    return ProfileService(
        repo=ProfileRepository(conn),
        gate_model=build_gate_model(),
        now=lambda: datetime.now(tz=UTC),
    )


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
    from datetime import UTC, datetime

    settings = get_settings()
    conn = connect(settings.db_path)
    apply_schema(conn)

    service = get_service()
    return ChatService(
        deps=service._deps,
        messages=MessageRepository(conn),
        checkpointer=SqliteSaver(connect(Path(str(settings.db_path) + ".chat-checkpoints"))),
        now=lambda: datetime.now(tz=UTC),
        profile=get_profile_service(),
    )
