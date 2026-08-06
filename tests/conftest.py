"""Shared pytest fixtures. Populated as tasks add fixtures."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data.db import apply_schema, connect
from knowledge.ingest import load_corpus
from knowledge.retriever import ChromaRetriever, build_vectorstore
from tests.fakes.embeddings import HashingEmbeddings


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Every test runs with a dummy API key so Settings never fails to construct."""
    monkeypatch.setenv("PLANTOPIA_OPENROUTER_API_KEY", "sk-test")


@pytest.fixture
def db():
    """In-memory database with the full schema applied."""
    conn = connect(":memory:")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def now():
    """A fixed instant. Never use wall-clock time in tests."""
    fixed = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return lambda: fixed


@pytest.fixture(scope="session")
def fixture_corpus():
    """Chunks parsed from the real corpus directory."""
    return load_corpus(Path("knowledge/corpus"))


@pytest.fixture
def chroma_retriever(fixture_corpus):
    """An in-memory Chroma retriever over the corpus, using offline embeddings.

    The same ``HashingEmbeddings`` instance serves both paths: it satisfies the
    LangChain ``Embeddings`` interface for text and exposes ``embed_image`` for the
    cross-modal path, so neither path touches a network. A uuid suffix on the
    collection name keeps each test's collection isolated from every other test.
    """
    embeddings = HashingEmbeddings()
    store = build_vectorstore(
        chunks=fixture_corpus,
        embeddings=embeddings,
        collection_name=f"test-corpus-{uuid.uuid4().hex}",
    )
    return ChromaRetriever(store, embeddings)
