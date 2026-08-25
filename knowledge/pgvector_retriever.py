"""Corpus retrieval over pgvector.

**Nothing uses this yet.** Retrieval runs on ``ChromaRetriever``; the move waits until
the embedding model is chosen, because a different model means re-embedding the corpus
anyway (``docs/known-limitations.md``, M25). This implements the same ``Retriever``
Protocol and shares the same merge logic (``knowledge.merging``), so wiring it in later
is a construction change rather than a rewrite.

**Scores.** LangChain's Chroma wrapper reports relevance as ``1.0 - cosine_distance``.
pgvector's ``<=>`` *is* cosine distance, so ``1 - (embedding <=> query)`` is the same
number by the same definition rather than one that happens to look similar. The two do
not agree to the last bit — Chroma normalises vectors in float32 when storing them and
compares by inner product — and they cannot be made to, because the embedding provider
does not reproduce its own vectors either (M24).

**No index.** 301 rows scan exactly and in under a millisecond. An approximate index
(HNSW) may reorder results by construction, and there is nothing to buy with that
ambiguity at this size.
"""

from collections.abc import Sequence

from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent.schemas import LoadedImage, Passage
from data.models import CorpusChunk
from knowledge.merging import PER_DOC_SECTIONS, keep_best, ranked


class PgVectorRetriever:
    """Multi-query retrieval with deduplication and best-score merging."""

    def __init__(self, session: Session, embeddings: Embeddings) -> None:
        self._session = session
        self._embeddings = embeddings
        self._doc_ids: tuple[str, ...] | None = None

    def search(
        self, queries: Sequence[str], k: int, *, sections: Sequence[str] | None = None
    ) -> list[Passage]:
        """The best passage from each of the ``k`` best-matching disorders.

        One passage per disorder, deliberately: sections of the same document otherwise
        compete for slots, and a document whose language is broad enough to match almost
        anything takes several of the six and crowds out other candidates entirely.

        ``sections`` restricts what may match, and callers should restrict it — some
        sections describe *other* disorders in order to contrast with them, and so act
        as attractors for exactly the wrong query.
        """
        if not queries:
            return []
        return self.search_by_vectors(
            [self._embeddings.embed_query(query) for query in queries], k, sections=sections
        )

    def search_by_vectors(
        self, vectors: Sequence[Sequence[float]], k: int, *, sections: Sequence[str] | None = None
    ) -> list[Passage]:
        """``search``, with the embedding step already done.

        Separate so that retrieval can be exercised without an embedding client at all —
        which is how this file is tested, and the only way to compare two retrievers on
        an identical question rather than on two embeddings of the same text.
        """
        best: dict[tuple[str, str], Passage] = {}
        per_query = k * (len(sections) if sections else PER_DOC_SECTIONS)

        for vector in vectors:
            distance = CorpusChunk.embedding.cosine_distance(vector)
            statement = select(CorpusChunk, distance.label("distance"))
            if sections:
                statement = statement.where(CorpusChunk.section.in_(list(sections)))
            # doc_id and section break ties, so repeating a search cannot reorder equally
            # scored passages. Exact ties are vanishingly unlikely across 1536
            # dimensions; determinism should not rest on that.
            statement = statement.order_by(distance, CorpusChunk.doc_id, CorpusChunk.section).limit(
                per_query
            )

            for chunk, chunk_distance in self._session.execute(statement):
                keep_best(
                    best,
                    doc_id=chunk.doc_id,
                    section=chunk.section,
                    text=chunk.content,
                    score=1.0 - chunk_distance,
                )

        return ranked(best, k)

    def sections_for(self, doc_ids: Sequence[str], sections: Sequence[str]) -> list[Passage]:
        """Named sections of named documents, fetched by id.

        A lookup rather than a search: no embedding call, no ranking, and no way for a
        wanted section to miss because something else scored above it. This is what
        makes reasoning-before-retrieval work — a correct document sitting at rank 21 of
        43 still reaches the model once something names it.

        Ids that do not exist are skipped; a corpus document without an optional section
        is a normal state.

        Scored 0.0, because these passages were not ranked and a similarity score for
        them would be fiction. Nothing filters on the score of retrieved passages; the
        one consumer, ``tools.web_search.retrieval_was_weak``, reads the maximum, which
        the searched passages already set.
        """
        if not doc_ids or not sections:
            return []

        rows = self._session.scalars(
            select(CorpusChunk)
            .where(
                CorpusChunk.doc_id.in_(list(doc_ids)),
                CorpusChunk.section.in_(list(sections)),
            )
            .order_by(CorpusChunk.doc_id, CorpusChunk.section)
        ).all()
        return [
            Passage(doc_id=row.doc_id, section=row.section, text=row.content, score=0.0)
            for row in rows
        ]

    def known_doc_ids(self) -> tuple[str, ...]:
        """Every disorder in the corpus, sorted.

        Cached: the corpus is fixed for the life of the process, and this is called once
        per diagnosis to tell a model which names it is allowed to use.
        """
        if self._doc_ids is None:
            rows = self._session.scalars(select(CorpusChunk.doc_id).distinct()).all()
            self._doc_ids = tuple(sorted(rows))
        return self._doc_ids

    @property
    def supports_image_search(self) -> bool:
        """Always false while no embedding model that accepts images is reachable.

        Reported rather than silently returning text results: the enrich node asks this
        before searching, and skipping the call is what keeps ``search_by_photograph``
        out of the tools it reports as used. Telling the owner a second opinion was
        sought that never was is worse than not seeking it.
        """
        return False

    def search_by_image(self, images: Sequence[LoadedImage], k: int) -> list[Passage]:
        """Nothing, for as long as ``supports_image_search`` is false.

        Kept rather than dropped because the Protocol declares it and the enrich node's
        skip-path is tested against it. When a multimodal embedder becomes reachable
        (``U2``), this is where it goes.
        """
        return []
