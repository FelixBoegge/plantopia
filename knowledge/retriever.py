"""Chroma-backed retrieval over the disorder corpus.

Retrieval is multi-query: the caller issues one query per extracted symptom plus a
combined query, and this module merges the result sets, keeping the best score for
any passage that several queries found.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from agent.schemas import ImageRef, Passage
from core.embeddings import ImageEmbedder
from knowledge.ingest import Chunk


class Retriever(Protocol):
    """What the enrich node needs from retrieval."""

    def search(self, queries: Sequence[str], k: int) -> list[Passage]:
        """Return the best ``k`` passages across every query, best first."""
        ...

    @property
    def supports_image_search(self) -> bool:
        """Whether the cross-modal path is wired at all.

        Distinct from ``search_by_image`` returning nothing: this says the search
        cannot happen, not that it happened and found nothing. Callers report tool
        use to the user, and must not claim a search that structurally could not run.
        """
        ...

    def search_by_image(self, images: Sequence[ImageRef], k: int) -> list[Passage]:
        """Return corpus passages that match the photographs themselves.

        Cross-modal: the image is embedded into the same space as the corpus text.
        Scores from this method are NOT comparable with scores from ``search`` and
        must never be merged into one ranked list (spec §10.4).
        """
        ...


def build_vectorstore(
    *,
    chunks: Sequence[Chunk],
    embeddings: Embeddings,
    collection_name: str = "plantopia",
    persist_directory: Path | None = None,
) -> Chroma:
    """Build a Chroma collection from corpus chunks."""
    documents = [
        Document(
            id=f"{chunk.doc_id}::{chunk.section}",
            page_content=f"{chunk.name} — {chunk.section}\n\n{chunk.text}",
            metadata={
                "doc_id": chunk.doc_id,
                "name": chunk.name,
                "section": chunk.section,
                "category": chunk.category,
                "transmissible": chunk.transmissible,
                "severity": chunk.severity,
            },
        )
        for chunk in chunks
    ]
    return Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=str(persist_directory) if persist_directory else None,
        collection_metadata={"hnsw:space": "cosine"},
    )


class ChromaRetriever:
    """Multi-query retrieval with deduplication and best-score merging.

    Two independent paths. ``search`` embeds text queries derived from the extracted
    symptoms. ``search_by_image`` embeds the photographs themselves. They fail
    independently, which is the reason both exist — but their scores live on
    different scales, so callers must keep the results apart.
    """

    def __init__(self, vectorstore: Chroma, image_embedder: ImageEmbedder | None = None) -> None:
        self._store = vectorstore
        self._image_embedder = image_embedder

    def search(self, queries: Sequence[str], k: int) -> list[Passage]:
        best: dict[tuple[str, str], Passage] = {}

        for query in queries:
            for document, score in self._store.similarity_search_with_relevance_scores(query, k=k):
                self._keep_best(best, document, score)

        return self._ranked(best, k)

    @property
    def supports_image_search(self) -> bool:
        return self._image_embedder is not None

    def search_by_image(self, images: Sequence[ImageRef], k: int) -> list[Passage]:
        """Retrieve corpus passages by embedding the photographs directly.

        Returns an empty list when no image embedder is configured or every embedding
        call fails — the caller then proceeds on the text path alone.
        """
        if self._image_embedder is None:
            return []

        best: dict[tuple[str, str], Passage] = {}

        for image in images:
            vector = self._image_embedder.embed_image(image.data_b64, image.media_type)
            if vector is None:
                continue
            results = self._store.similarity_search_by_vector_with_relevance_scores(vector, k=k)
            for document, score in results:
                self._keep_best(best, document, score)

        return self._ranked(best, k)

    @staticmethod
    def _keep_best(best: dict[tuple[str, str], Passage], document: Document, score: float) -> None:
        passage = Passage(
            doc_id=document.metadata["doc_id"],
            section=document.metadata["section"],
            text=document.page_content,
            score=max(0.0, min(1.0, float(score))),
        )
        key = (passage.doc_id, passage.section)
        existing = best.get(key)
        if existing is None or passage.score > existing.score:
            best[key] = passage

    @staticmethod
    def _ranked(best: dict[tuple[str, str], Passage], k: int) -> list[Passage]:
        return sorted(best.values(), key=lambda p: p.score, reverse=True)[:k]
