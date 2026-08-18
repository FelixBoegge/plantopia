"""Knowledge-base search.

Query construction lives here rather than in the retriever because the queries are
derived from extracted symptoms, which is domain logic rather than storage logic.
"""

from collections.abc import Sequence

from agent.schemas import Passage, SymptomSet
from knowledge.retriever import Retriever


def build_symptom_queries(symptoms: SymptomSet, species: str | None) -> list[str]:
    """Build one query per symptom plus one combined query.

    Symptom position is included because it is the most discriminating feature —
    interveinal yellowing and leaf-tip yellowing have different causes.
    """
    prefix = f"{species}: " if species else ""

    queries = [
        f"{prefix}{symptom.description} on {symptom.position.value.replace('_', ' ')}"
        for symptom in symptoms.symptoms
    ]

    combined_parts = [s.description for s in symptoms.symptoms]
    if symptoms.soil_condition:
        combined_parts.append(f"soil is {symptoms.soil_condition}")
    queries.append(f"{prefix}{', '.join(combined_parts)}")

    return queries


# The sections that describe *this* disorder, and so the only ones a symptom query
# should be allowed to match. The rest either describe other disorders or discuss
# treatment, and matching against them retrieves the wrong document: measured on a
# nitrogen case, ``phosphorus-deficiency``'s look-alikes section outscored
# ``nitrogen-deficiency``'s own symptoms, because it recites nitrogen's symptoms in
# order to contrast them. A look-alikes section is an attractor for precisely the
# disorder it is trying to rule out.
MATCHABLE_SECTIONS = ("Symptoms", "Where on the plant symptoms appear")

# The section that separates a disorder from the things it is mistaken for. Every
# corpus document has one (knowledge/ingest.py enforces it), and it is written for
# exactly the confusions the diagnosis keeps making: nitrogen-deficiency's says that
# magnesium leaves veins green while nitrogen yellows them too, and that natural
# senescence takes one old leaf at a time rather than a band of them. Fetched by id
# for the shortlist rather than matched, for the reason above.
DISCRIMINATING_SECTION = "Look-alikes and how to tell them apart"


def search_plant_knowledge(
    retriever: Retriever,
    queries: Sequence[str],
    k: int = 6,
) -> list[Passage]:
    """Search the curated corpus, then add the shortlist's discriminating sections.

    Similarity search alone answers "which disorders look like this", which is the
    wrong question once several do. A measured run retrieved the correct document for
    every nutrient case and still got four of six wrong, because what came back was
    the *Symptoms* section of each candidate — six descriptions of similar-looking
    problems and nothing about how to tell them apart. Where a look-alikes section did
    appear it belonged to a competitor, so the model read a rival's case for itself and
    none for the truth.

    Those sections cannot be left to ranking: they describe *other* disorders, so they
    match a query about this plant's symptoms less well than the symptom sections they
    would have to outrank. Fetching them by id once a document is in contention is the
    only way they arrive reliably.

    Returns an empty list when given no queries.
    """
    if not queries:
        return []

    shortlist = retriever.search(queries, k=k, sections=MATCHABLE_SECTIONS)
    if not shortlist:
        return []

    discriminators = retriever.sections_for(
        [passage.doc_id for passage in shortlist], [DISCRIMINATING_SECTION]
    )

    # Ranked material first, then the discriminators, rather than interleaved by
    # score: the fetched sections carry no meaningful score, and the ranking is what
    # tells the reader which candidates were actually matched.
    already = {(p.doc_id, p.section) for p in shortlist}
    return shortlist + [p for p in discriminators if (p.doc_id, p.section) not in already]
