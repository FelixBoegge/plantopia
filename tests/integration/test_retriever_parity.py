"""Do the two retrievers answer the same question the same way?

Temporary, and deliberately so: it exists to license deleting Chroma and is removed with
it. Keeping a test of a store that no longer exists is how documentation ends up citing
modules nobody can open.

**This is the gate that stands in for an evaluation run.** The embedding model is not
changing, so every stored vector is the same vector and a $1.55 harness run would be
paying to be told nothing moved. What is genuinely unverified is whether
``PgVectorRetriever`` *ranks* the way ``ChromaRetriever`` does, and that is a question
about two implementations rather than about two models — so it is answered here, offline
and for nothing.

**Both stores are built from one embedder, so a difference is the implementation.** The
alternative — comparing the real corpus vectors in ``corpus_chunks`` against a freshly
embedded Chroma store — cannot be exact: ``M24`` measured the provider disagreeing with
its own earlier output on 38 of 87 query strings, moving merged scores by up to 1.1e-3.
Feeding both stores identical vectors removes that variable entirely, which is what makes
a strict assertion on ranking defensible.

What it still cannot demand is the last bit. Chroma normalises in float32 and compares by
inner product; pgvector's ``<=>`` is cosine distance, and LangChain's Chroma wrapper
reports ``1.0 - distance``. Those are the same definition arrived at by different
arithmetic, so this asserts the passage *set* and the leading ranks, and reports a
tail difference rather than failing on one.

Run explicitly — ``integration`` is excluded from the default suite:

    uv run pytest tests/integration/test_retriever_parity.py -m integration -s --no-cov
"""

import uuid
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
from eval.cases import load_cases
from knowledge.ingest import chunk_text
from knowledge.pgvector_retriever import PgVectorRetriever
from knowledge.retriever import ChromaRetriever, build_vectorstore
from tests.fakes.embeddings import HashingEmbeddings
from tools.knowledge import build_symptom_queries

pytestmark = pytest.mark.integration

GOLDEN_SET = Path("eval/golden_set")

# What retrieval asks for in the application: ``KNOWLEDGE_RESULTS`` in agent/nodes/enrich.
K = 6

# How many leading ranks must agree exactly. Below this a swap is a real disagreement
# about which disorder is most likely; at the tail it is two candidates a thousandth apart.
STABLE_RANKS = 5


class _WidenedHashingEmbeddings(Embeddings):
    """``HashingEmbeddings`` widened to the corpus column's fixed width.

    ``corpus_chunks.embedding`` is ``vector(1536)`` and cannot hold anything narrower;
    ``HashingEmbeddings`` produces 256 dimensions. Zero-padding leaves every dot product
    and every norm unchanged, so cosine similarity — and therefore the ranking and the
    scores both retrievers compute — is exactly the geometry ``HashingEmbeddings`` gives.

    One instance embeds both stores. That is the point: it makes the vectors a constant so
    that anything this test finds is attributable to the SQL or the merge, and not to a
    provider that does not reproduce itself (``M24``).
    """

    def __init__(self) -> None:
        self._inner = HashingEmbeddings()

    def _widen(self, vector: list[float]) -> list[float]:
        return vector + [0.0] * (EMBEDDING_DIMENSIONS - len(vector))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._widen(v) for v in self._inner.embed_documents(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self._widen(self._inner.embed_query(text))


@pytest.fixture(scope="module")
def embeddings() -> _WidenedHashingEmbeddings:
    return _WidenedHashingEmbeddings()


@pytest.fixture
def chroma(fixture_corpus, embeddings) -> ChromaRetriever:
    """The outgoing path, over the real corpus. A uuid on the collection keeps it its own."""
    store = build_vectorstore(
        chunks=fixture_corpus,
        embeddings=embeddings,
        collection_name=f"parity-{uuid.uuid4().hex}",
    )
    return ChromaRetriever(store, embeddings)


@pytest.fixture
def pgvector(db, fixture_corpus, embeddings) -> PgVectorRetriever:
    """The incoming path, over the same corpus and the same vectors.

    Written into the test database rather than read from the development one: the rows
    there hold the *provider's* vectors, which would reintroduce exactly the variable this
    test removes. ``content`` is ``chunk_text`` because that is what both
    ``build_vectorstore`` and ``knowledge.ingest_corpus`` embed — a different string is a
    different vector.
    """
    texts = [chunk_text(chunk) for chunk in fixture_corpus]
    vectors = embeddings.embed_documents(texts)
    db.add_all(
        [
            CorpusChunk(
                doc_id=chunk.doc_id,
                section=chunk.section,
                name=chunk.name,
                content=text,
                category=chunk.category,
                transmissible=chunk.transmissible,
                severity=chunk.severity,
                embedding=vector,
            )
            for chunk, text, vector in zip(fixture_corpus, texts, vectors, strict=True)
        ]
    )
    db.flush()
    return PgVectorRetriever(db, embeddings)


def _queries() -> list[str]:
    """Every query the golden set makes retrieval see.

    Built with the application's own ``build_symptom_queries`` rather than by hand, so the
    comparison is over the strings retrieval actually receives — one per symptom plus a
    combined one, each prefixed with the species.
    """
    return [
        query
        for case in load_cases(GOLDEN_SET)
        for query in build_symptom_queries(case.symptoms, case.plant.species)
    ]


def test_the_two_retrievers_return_the_same_passages(chroma, pgvector, capsys):
    queries = _queries()
    assert queries, "no queries built from the golden set"

    tail_differences = []

    for query in queries:
        from_chroma = [(p.doc_id, p.section) for p in chroma.search([query], k=K)]
        from_pgvector = [(p.doc_id, p.section) for p in pgvector.search([query], k=K)]

        assert set(from_chroma) == set(from_pgvector), (
            f"different passage sets for {query!r}:\n"
            f"  chroma:   {from_chroma}\n  pgvector: {from_pgvector}"
        )
        assert from_chroma[:1] == from_pgvector[:1], (
            f"the leading passage differs for {query!r}: "
            f"{from_chroma[:1]} vs {from_pgvector[:1]} — a real finding, not drift"
        )
        assert from_chroma[:STABLE_RANKS] == from_pgvector[:STABLE_RANKS], (
            f"ranks 1-{STABLE_RANKS} differ for {query!r}:\n"
            f"  chroma:   {from_chroma}\n  pgvector: {from_pgvector}"
        )

        if from_chroma != from_pgvector:
            tail_differences.append((query, from_chroma[-1], from_pgvector[-1]))

    # Reported, not failed: a rank-6 swap between two candidates a thousandth apart is
    # arithmetic, not a regression. The count goes into M25's register entry.
    with capsys.disabled():
        print(f"\n{len(tail_differences)} of {len(queries)} queries differ at rank {K}")
        for query, chroma_tail, pgvector_tail in tail_differences[:10]:
            print(f"  {query[:60]!r}: {chroma_tail} vs {pgvector_tail}")


def test_the_two_retrievers_agree_on_scores(chroma, pgvector):
    """The two score definitions are one definition reached by different arithmetic.

    Chroma normalises in float32 and compares by inner product, reporting
    ``1.0 - distance``; pgvector computes ``1 - (embedding <=> query)`` where ``<=>`` *is*
    cosine distance. Identical vectors, so the only gap left is representation.
    """
    for query in _queries()[:20]:
        from_chroma = {(p.doc_id, p.section): p.score for p in chroma.search([query], k=K)}
        for passage in pgvector.search([query], k=K):
            counterpart = from_chroma.get((passage.doc_id, passage.section))
            if counterpart is None:
                continue
            assert passage.score == pytest.approx(counterpart, abs=1e-3), (
                f"{passage.doc_id}/{passage.section} for {query!r}: "
                f"{passage.score} vs {counterpart} — the score definitions differ"
            )


def test_both_know_the_same_corpus(chroma, pgvector):
    """``known_doc_ids`` feeds ``hypothesise``, which asks a model to name disorders and
    then looks them up. A store that knows a different set answers a different question."""
    assert pgvector.known_doc_ids() == chroma.known_doc_ids()


def test_fetching_named_sections_by_id_agrees(chroma, pgvector):
    """``sections_for`` bypasses ranking entirely — it is how the look-alikes sections and
    the documents ``hypothesise`` named are fetched. Keyed by ``(doc_id, section)`` in
    Postgres and by the ``doc_id::section`` ids it replaces in Chroma, so this is the one
    comparison that checks the key survived the move."""
    doc_ids = list(chroma.known_doc_ids())[:6]
    sections = ["Symptoms", "Look-alikes and how to tell them apart"]

    from_chroma = sorted((p.doc_id, p.section) for p in chroma.sections_for(doc_ids, sections))
    from_pgvector = sorted((p.doc_id, p.section) for p in pgvector.sections_for(doc_ids, sections))

    assert from_pgvector == from_chroma
