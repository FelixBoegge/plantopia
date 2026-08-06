"""Wire the real dependencies once per Streamlit session."""

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
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.roadmap import RoadmapRepository
from knowledge.ingest import load_corpus
from knowledge.retriever import ChromaRetriever, build_vectorstore
from services.diagnosis_service import DiagnosisService
from tools.care_profiles import lookup_plant_care_profile
from tools.weather import get_local_weather
from tools.web_search import web_search_plant_info


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
    image_embedder = ImageEmbedder(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.embedding_model,
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
        now=lambda: datetime.now(tz=UTC),
    )

    checkpointer = SqliteSaver(connect(Path(str(settings.db_path) + ".checkpoints")))
    graph = build_diagnosis_graph(deps, checkpointer)

    return DiagnosisService(deps, graph, upload_dir=settings.upload_path)
