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

# How many sections a corpus document has, and so the factor by which a query must
# over-fetch to still find k distinct disorders once each document keeps only one
# passage. See ``knowledge/ingest.py``'s REQUIRED_SECTIONS.
_PER_DOC_SECTIONS = 7


class Retriever(Protocol):
    """What the enrich node needs from retrieval."""

    def search(
        self, queries: Sequence[str], k: int, *, sections: Sequence[str] | None = None
    ) -> list[Passage]:
        """Return the best ``k`` passages across every query, best first.

        At most one passage per disorder, so ``k`` slots describe ``k`` candidates.
        ``sections`` restricts which sections may match at all; ``None`` allows any.
        """
        ...

    def sections_for(self, doc_ids: Sequence[str], sections: Sequence[str]) -> list[Passage]:
        """Fetch named sections of named documents directly, by id rather than by score.

        For material a caller knows it wants once a document is in contention, which
        similarity search will not reliably surface on its own — see
        ``tools.knowledge.search_plant_knowledge``.
        """
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

    def search(
        self, queries: Sequence[str], k: int, *, sections: Sequence[str] | None = None
    ) -> list[Passage]:
        """The best passage from each of the ``k`` best-matching disorders.

        One passage per disorder, deliberately. Sections of the same document compete
        with each other for slots otherwise, and a document whose language is broad
        enough to match almost anything — ``insufficient-light``, ``poor-drainage``,
        ``salt-buildup`` — takes two or three of the six, crowding out other candidates
        entirely. A measured run had every nutrient case retrieve six passages covering
        only four disorders, a distractor holding three of them and the correct answer
        holding one: a differential built from that reads the crowder as the
        better-supported explanation, because it is better represented.

        ``sections`` restricts what may match. Callers should restrict it, because some
        sections describe *other* disorders in order to contrast with them, and so act
        as attractors for exactly the wrong query — ``phosphorus-deficiency``'s
        look-alikes section outscored ``nitrogen-deficiency``'s own symptoms on a
        nitrogen query, because it recites nitrogen's symptoms to distinguish them.
        """
        best: dict[tuple[str, str], Passage] = {}
        # Over-fetch, because collapsing to one passage per disorder discards most of
        # what one query returns. Bounded by how many sections a document can offer.
        per_query = k * (len(sections) if sections else _PER_DOC_SECTIONS)
        where = {"section": {"$in": list(sections)}} if sections else None

        for query in queries:
            results = self._store.similarity_search_with_relevance_scores(
                query, k=per_query, filter=where
            )
            for document, score in results:
                self._keep_best(best, document, score)

        return self._ranked(best, k)

    def sections_for(self, doc_ids: Sequence[str], sections: Sequence[str]) -> list[Passage]:
        """Named sections of named documents, fetched by id.

        A lookup rather than a search: ids are ``"{doc_id}::{section}"`` by
        construction in ``build_vectorstore``, so this costs no embedding call and
        cannot miss a section for ranking below something else. Ids that do not exist
        are skipped — a corpus document without an optional section is a normal state.

        Scored 0.0, because these passages were not ranked and a similarity score for
        them would be fiction. Nothing filters on the score of retrieved passages; the
        one consumer, ``tools.web_search.retrieval_was_weak``, reads the maximum, which
        the searched passages already set.
        """
        wanted = [f"{doc_id}::{section}" for doc_id in doc_ids for section in sections]
        if not wanted:
            return []

        found = self._store.get(ids=wanted, include=["metadatas", "documents"])
        return [
            Passage(
                doc_id=metadata["doc_id"],
                section=metadata["section"],
                text=text,
                score=0.0,
            )
            for metadata, text in zip(found["metadatas"], found["documents"], strict=True)
        ]

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
        """The best ``k`` passages, at most one per disorder.

        Scores across nutrient cases sit within about 0.03 of each other, so which
        disorder wins is close to arbitrary; what is not arbitrary is how many slots
        each one occupies. Capping at one per document turns ``k`` passages into ``k``
        distinct candidates.
        """
        ordered = sorted(best.values(), key=lambda p: p.score, reverse=True)
        kept: list[Passage] = []
        seen: set[str] = set()
        for passage in ordered:
            if passage.doc_id in seen:
                continue
            kept.append(passage)
            seen.add(passage.doc_id)
            if len(kept) == k:
                break
        return kept
