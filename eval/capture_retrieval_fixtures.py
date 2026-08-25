"""Record what the Chroma retriever returns, so the pgvector one can be held to it.

    uv run python -m eval.capture_retrieval_fixtures

This is the baseline half of the parity gate in ``specs/disorder-retrieval``. It runs
once, against the retriever being replaced, and commits its answers. The test then
replays the *same query vectors* through the new implementation and demands the same
document ids, sections and ordering.

**Why vectors and not query text.** If each side embedded the text itself, a difference
in results could mean a difference in retrieval *or* a difference in embedding, and the
gate could not tell you which. Capturing the vector removes that ambiguity: both sides
are asked the identical question.

**What it costs.** One embedding call per distinct query — roughly a hundred short
strings, a few thousand tokens, well under a cent at text-embedding-3-small's price.
It is the only API call anywhere in the gate; the test itself makes none, which is why
it can run in CI.
"""

import argparse
import logging
from pathlib import Path

from eval.cases import load_cases
from eval.retrieval_fixtures import FIXTURE_PATH, dump
from tools.knowledge import DISCRIMINATING_SECTION, MATCHABLE_SECTIONS, build_symptom_queries

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = FIXTURE_PATH
GOLDEN_SET = Path("eval/golden_set")
K = 6

# Every golden case retrieves *well* — the whole set scores above the escalation
# threshold, so recording only those would test the "do not escalate" branch and leave
# the branch that actually calls the web unexercised. These are deliberately outside
# the corpus's subject, so they score low and escalation fires.
ESCALATION_PROBES = (
    "how do I replace the timing belt on a diesel engine",
    "what is the capital city of Portugal",
    "recipe for sourdough starter using rye flour",
)


def capture(settings, output: Path) -> dict:
    """Replay every golden case's retrieval and write down the answers."""
    from core.llm import build_embeddings
    from knowledge.ingest import load_corpus
    from knowledge.retriever import ChromaRetriever, build_vectorstore

    embeddings = build_embeddings()
    store = build_vectorstore(
        chunks=load_corpus(settings.corpus_path),
        embeddings=embeddings,
        persist_directory=settings.chroma_path,
    )
    retriever = ChromaRetriever(store, None)

    cases = load_cases(GOLDEN_SET)
    per_query = K * len(MATCHABLE_SECTIONS)
    where = {"section": {"$in": list(MATCHABLE_SECTIONS)}}

    searches, fetches = [], []
    for case in cases:
        queries = build_symptom_queries(case.symptoms, case.plant.species)

        # Each query on its own, so a difference can be attributed to one query rather
        # than to the merge.
        for query in queries:
            vector = embeddings.embed_query(query)
            results = store.similarity_search_by_vector_with_relevance_scores(
                vector, k=per_query, filter=where
            )
            searches.append(
                {
                    "case_id": case.id,
                    "query": query,
                    "vector": vector,
                    "k": per_query,
                    "sections": list(MATCHABLE_SECTIONS),
                    "results": [
                        {
                            "doc_id": document.metadata["doc_id"],
                            "section": document.metadata["section"],
                            "score": score,
                        }
                        for document, score in results
                    ],
                }
            )

        # The merged answer the pipeline actually consumes, plus the escalation
        # decision that hangs off its best score. A ranking-only comparison would let a
        # uniform score shift flip web search on or off unnoticed.
        merged = retriever.search(queries, k=K, sections=MATCHABLE_SECTIONS)
        best = max((p.score for p in merged), default=0.0)
        searches.append(
            {
                "case_id": case.id,
                "query": None,
                "merged_for": queries,
                "k": K,
                "sections": list(MATCHABLE_SECTIONS),
                "results": [
                    {"doc_id": p.doc_id, "section": p.section, "score": p.score} for p in merged
                ],
                "best_score": best,
                "escalates": best < settings.retrieval_score_threshold,
            }
        )

        # Fetch-by-id: the path hypothesis-driven retrieval depends on, and the one
        # where ranking must play no part at all.
        wanted = sorted({case.ground_truth, *case.also_acceptable})
        for sections in (list(MATCHABLE_SECTIONS), [DISCRIMINATING_SECTION]):
            fetched = retriever.sections_for(wanted, sections)
            fetches.append(
                {
                    "case_id": case.id,
                    "doc_ids": wanted,
                    "sections": sections,
                    "results": [
                        {"doc_id": p.doc_id, "section": p.section, "score": p.score}
                        for p in fetched
                    ],
                }
            )

    probes = []
    for query in ESCALATION_PROBES:
        vector = embeddings.embed_query(query)
        found = store.similarity_search_by_vector_with_relevance_scores(
            vector, k=per_query, filter=where
        )
        merged = retriever.search([query], k=K, sections=MATCHABLE_SECTIONS)
        best = max((p.score for p in merged), default=0.0)
        probes.append(
            {
                "query": query,
                "vector": vector,
                "k": per_query,
                "sections": list(MATCHABLE_SECTIONS),
                "results": [
                    {
                        "doc_id": document.metadata["doc_id"],
                        "section": document.metadata["section"],
                        "score": score,
                    }
                    for document, score in found
                ],
                "best_score": best,
                "escalates": best < settings.retrieval_score_threshold,
            }
        )

    fixture = {
        "embedding_model": settings.embedding_model,
        "retrieval_score_threshold": settings.retrieval_score_threshold,
        "known_doc_ids": list(retriever.known_doc_ids()),
        "searches": searches,
        "fetches": fetches,
        "escalation_probes": probes,
    }
    dump(fixture, output)
    return {
        "cases": len(cases),
        "searches": len(searches),
        "fetches": len(fetches),
        "output": str(output),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    from core.config import get_settings

    summary = capture(get_settings(), args.output)
    print(
        f"{summary['cases']} cases -> {summary['searches']} searches and "
        f"{summary['fetches']} fetches recorded in {summary['output']}"
    )


if __name__ == "__main__":
    main()
