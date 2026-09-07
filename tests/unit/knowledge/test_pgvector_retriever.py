"""The pgvector retriever, on its own terms.

The only retrieval path there is, as of 2026-09-07. These tests hold it honest against a
small synthetic corpus with vectors chosen so the expected ordering is arithmetic rather
than a guess — which is what the real corpus cannot give you, its ranking being a fact
about the corpus rather than about this code.

No embedding calls: every test supplies vectors directly.
"""

import math

import pytest

from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
from knowledge.pgvector_retriever import PgVectorRetriever

SYMPTOMS = "Symptoms"
LOOKALIKES = "Look-alikes and how to tell them apart"


def _vector(*, angle: float) -> list[float]:
    """A unit vector in the first two dimensions, at ``angle`` radians.

    Cosine similarity between two of these is the cosine of the angle between them, so
    the expected score of every comparison below is something a reader can work out.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = math.cos(angle)
    vector[1] = math.sin(angle)
    return vector


def _chunk(doc_id: str, section: str, angle: float) -> CorpusChunk:
    return CorpusChunk(
        doc_id=doc_id,
        section=section,
        name=doc_id.replace("-", " ").title(),
        content=f"{doc_id} / {section}",
        category="watering",
        transmissible=False,
        severity="act_this_week",
        embedding=_vector(angle=angle),
    )


@pytest.fixture
def retriever(db):
    """Four disorders at increasing angles from the query direction, so the expected
    ranking is exactly the order they were defined in."""
    db.add_all(
        [
            _chunk("overwatering", SYMPTOMS, 0.0),
            _chunk("overwatering", LOOKALIKES, 0.6),
            _chunk("root-rot", SYMPTOMS, 0.2),
            _chunk("nitrogen-deficiency", SYMPTOMS, 0.4),
            _chunk("spider-mites", SYMPTOMS, 1.2),
        ]
    )
    db.flush()
    return PgVectorRetriever(db, embeddings=None)


def test_results_come_back_best_first(retriever):
    found = retriever.search_by_vectors([_vector(angle=0.0)], k=4)

    assert [p.doc_id for p in found] == [
        "overwatering",
        "root-rot",
        "nitrogen-deficiency",
        "spider-mites",
    ]


def test_scores_are_cosine_similarity(retriever):
    """1 - cosine distance, which for unit vectors is the cosine of the angle between
    them. Asserted against the arithmetic rather than against a recorded number."""
    found = retriever.search_by_vectors([_vector(angle=0.0)], k=4)
    scores = {p.doc_id: p.score for p in found}

    assert scores["overwatering"] == pytest.approx(1.0, abs=1e-6)
    assert scores["root-rot"] == pytest.approx(math.cos(0.2), abs=1e-6)
    assert scores["nitrogen-deficiency"] == pytest.approx(math.cos(0.4), abs=1e-6)


def test_k_limits_the_result_count(retriever):
    assert len(retriever.search_by_vectors([_vector(angle=0.0)], k=2)) == 2


def test_one_passage_per_disorder(retriever):
    """Sections of one document otherwise compete for slots, and a broadly-worded
    document takes several of the six."""
    found = retriever.search_by_vectors([_vector(angle=0.3)], k=4)

    assert len({p.doc_id for p in found}) == len(found)


def test_sections_restrict_what_can_match(retriever):
    found = retriever.search_by_vectors([_vector(angle=0.6)], k=4, sections=[LOOKALIKES])

    assert [(p.doc_id, p.section) for p in found] == [("overwatering", LOOKALIKES)]


def test_several_queries_merge_keeping_the_better_score(retriever):
    """A passage found by two queries is kept once, at its higher score."""
    near = retriever.search_by_vectors([_vector(angle=0.2)], k=1)[0]
    merged = retriever.search_by_vectors([_vector(angle=0.2), _vector(angle=1.2)], k=4)

    same = next(p for p in merged if p.doc_id == near.doc_id)
    assert same.score == pytest.approx(near.score, abs=1e-6)
    assert [p.doc_id for p in merged].count(near.doc_id) == 1


def test_repeating_a_search_returns_the_same_order(retriever):
    """Ordering breaks ties on doc_id and section, so determinism does not rest on
    floating-point luck."""
    first = retriever.search_by_vectors([_vector(angle=0.35)], k=4)
    second = retriever.search_by_vectors([_vector(angle=0.35)], k=4)

    assert [(p.doc_id, p.section, p.score) for p in first] == [
        (p.doc_id, p.section, p.score) for p in second
    ]


def test_no_queries_returns_nothing(retriever):
    assert retriever.search([], k=4) == []


def test_fetch_by_identifier_ignores_ranking(retriever):
    """The whole point: a document similarity would never surface still arrives when
    something names it."""
    found = retriever.sections_for(["spider-mites"], [SYMPTOMS])

    assert [p.doc_id for p in found] == ["spider-mites"]


def test_fetched_passages_carry_no_score(retriever):
    """They were not ranked, and a similarity score for them would be fiction."""
    assert all(p.score == 0.0 for p in retriever.sections_for(["overwatering"], [SYMPTOMS]))


def test_an_unknown_identifier_contributes_nothing(retriever):
    found = retriever.sections_for(["overwatering", "does-not-exist"], [SYMPTOMS])

    assert [p.doc_id for p in found] == ["overwatering"]


def test_fetching_nothing_asks_the_database_nothing(retriever):
    assert retriever.sections_for([], [SYMPTOMS]) == []
    assert retriever.sections_for(["overwatering"], []) == []


def test_known_document_ids_are_unique_and_sorted(retriever):
    assert retriever.known_doc_ids() == (
        "nitrogen-deficiency",
        "overwatering",
        "root-rot",
        "spider-mites",
    )
