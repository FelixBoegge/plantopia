"""Tests for multi-query retrieval and ranking, text and image paths."""

from agent.schemas import ImageRef, Passage
from knowledge.retriever import ChromaRetriever, build_vectorstore
from tests.fakes.embeddings import HashingEmbeddings


def test_search_returns_passages(chroma_retriever):
    results = chroma_retriever.search(["mushy brown roots"], k=3)
    assert results
    assert all(isinstance(p, Passage) for p in results)


def test_relevant_document_outranks_irrelevant_one(chroma_retriever):
    results = chroma_retriever.search(["fine webbing and stippling on leaves"], k=5)
    assert results[0].doc_id == "spider-mites"


def test_scores_are_probabilities_sorted_descending(chroma_retriever):
    results = chroma_retriever.search(["yellowing lower leaves wet soil"], k=5)
    scores = [p.score for p in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_multi_query_deduplicates_by_document_and_section(chroma_retriever):
    results = chroma_retriever.search(
        ["mushy brown roots", "brown mushy roots", "roots that are mushy and brown"],
        k=10,
    )
    keys = [(p.doc_id, p.section) for p in results]
    assert len(keys) == len(set(keys))


def test_multi_query_keeps_the_best_score_for_a_duplicate(chroma_retriever):
    single = chroma_retriever.search(["fine webbing between leaves"], k=10)
    multi = chroma_retriever.search(
        ["fine webbing between leaves", "completely unrelated aquarium filter"], k=10
    )
    best_single = max(p.score for p in single if p.doc_id == "spider-mites")
    best_multi = max(p.score for p in multi if p.doc_id == "spider-mites")
    assert best_multi >= best_single


def test_k_limits_the_result_count(chroma_retriever):
    assert len(chroma_retriever.search(["yellowing leaves"], k=2)) == 2


def test_empty_query_list_returns_nothing(chroma_retriever):
    assert chroma_retriever.search([], k=5) == []


def test_retriever_surfaces_the_lookalike_section(chroma_retriever):
    results = chroma_retriever.search(["how do I tell root rot from overwatering"], k=8)
    sections = {p.section for p in results}
    assert "Look-alikes and how to tell them apart" in sections


class TestImagePath:
    """Cross-modal retrieval (spec §10.4).

    Fake embeddings cannot produce meaningful image-to-text similarity, so these
    assert on structure — shape, ordering, k, degradation — never on which document
    a given image 'should' match. Semantic quality is measured by the evaluation
    harness against real embeddings, not here.
    """

    def _image(self, ref: str = "img-1") -> ImageRef:
        return ImageRef(ref=ref, media_type="image/png", data_b64="aGVsbG8=")

    def test_returns_passages(self, chroma_retriever):
        results = chroma_retriever.search_by_image([self._image()], k=3)
        assert results
        assert all(isinstance(p, Passage) for p in results)

    def test_results_are_sorted_descending(self, chroma_retriever):
        scores = [p.score for p in chroma_retriever.search_by_image([self._image()], k=5)]
        assert scores == sorted(scores, reverse=True)

    def test_k_limits_the_result_count(self, chroma_retriever):
        assert len(chroma_retriever.search_by_image([self._image()], k=2)) == 2

    def test_multiple_images_are_deduplicated(self, chroma_retriever):
        results = chroma_retriever.search_by_image([self._image("a"), self._image("b")], k=10)
        keys = [(p.doc_id, p.section) for p in results]
        assert len(keys) == len(set(keys))

    def test_no_images_returns_nothing(self, chroma_retriever):
        assert chroma_retriever.search_by_image([], k=5) == []

    def test_without_an_image_embedder_the_path_is_disabled(self, fixture_corpus):
        store = build_vectorstore(
            chunks=fixture_corpus,
            embeddings=HashingEmbeddings(),
            collection_name="test-no-image-embedder",
        )
        assert ChromaRetriever(store).search_by_image([self._image()], k=5) == []

    def test_an_embedding_failure_degrades_to_empty(self, fixture_corpus):
        class _FailingEmbedder:
            def embed_image(self, data_b64, media_type):
                return None

        store = build_vectorstore(
            chunks=fixture_corpus,
            embeddings=HashingEmbeddings(),
            collection_name="test-failing-embedder",
        )
        retriever = ChromaRetriever(store, _FailingEmbedder())
        assert retriever.search_by_image([self._image()], k=5) == []

    def test_the_text_path_still_works_when_the_image_path_fails(self, fixture_corpus):
        class _FailingEmbedder:
            def embed_image(self, data_b64, media_type):
                return None

        store = build_vectorstore(
            chunks=fixture_corpus,
            embeddings=HashingEmbeddings(),
            collection_name="test-text-still-works",
        )
        retriever = ChromaRetriever(store, _FailingEmbedder())
        assert retriever.search(["mushy brown roots"], k=3)
