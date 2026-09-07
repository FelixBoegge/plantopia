"""How retrieved passages are merged and ranked.

Extracted out of ``ChromaRetriever`` so the pgvector implementation could *share* it
rather than reproduce it, which is what made the comparison between the two answerable:
with the merge held constant, any difference had to be in the query. It found none — 0 of
87 golden-set queries differed at any rank — and Chroma was deleted, so this is now the
only ranking logic there is rather than the shared half of two.
"""

from agent.schemas import Passage

# How many sections a corpus document can offer. Used to over-fetch when no section
# filter is given, because collapsing to one passage per disorder discards most of what
# a single query returns.
PER_DOC_SECTIONS = 7


def keep_best(
    best: dict[tuple[str, str], Passage],
    *,
    doc_id: str,
    section: str,
    text: str,
    score: float,
) -> None:
    """Record a passage, keeping the higher score when the same one arrives twice.

    Scores are clamped to [0, 1]: a relevance score is presented to the model and shown
    in the UI, and a negative or above-one number there is noise rather than
    information.
    """
    passage = Passage(
        doc_id=doc_id,
        section=section,
        text=text,
        score=max(0.0, min(1.0, float(score))),
    )
    key = (passage.doc_id, passage.section)
    existing = best.get(key)
    if existing is None or passage.score > existing.score:
        best[key] = passage


def ranked(best: dict[tuple[str, str], Passage], k: int) -> list[Passage]:
    """The best ``k`` passages, at most one per disorder.

    Scores across nutrient cases sit within about 0.03 of each other, so which disorder
    wins is close to arbitrary; what is not arbitrary is how many slots each one
    occupies. Capping at one per document turns ``k`` passages into ``k`` distinct
    candidates.
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
