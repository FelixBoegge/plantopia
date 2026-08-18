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
    hypotheses: Sequence[str] = (),
) -> list[Passage]:
    """Gather reference material from two directions, then add the discriminators.

    **Similarity**, which answers "which corpus text resembles this description". It
    finds the obvious cases and nothing else: measured against the golden set, the
    correct document sat at rank 16, 17 and 21 of 43 for three of the six nutrient
    cases, because the owner's words and the corpus's are not near neighbours.

    **Named hypotheses**, fetched by id. ``agent/nodes/hypothesise.py`` asks the model
    which disorders are worth reading about, and rank stops mattering for those — a
    document at 21st is one lookup away once something names it. Where the two agree
    the document simply arrives once.

    **Discriminating sections** for everything on the combined shortlist. This is the
    material that decides *between* candidates, and it cannot be left to ranking: it
    describes other disorders, so it will always match this plant's symptoms less well
    than the symptom sections it would have to outrank.

    ``k`` bounds the similarity shortlist, not the total. Hypotheses add to it, and
    every shortlisted disorder contributes a discriminator.

    Returns an empty list when given neither queries nor hypotheses.
    """
    matched = retriever.search(queries, k=k, sections=MATCHABLE_SECTIONS) if queries else []

    # Hypothesised documents get the same descriptive sections a matched document
    # brings, so a candidate the model named is not argued about on thinner evidence
    # than one similarity happened to find.
    named = [doc_id for doc_id in hypotheses if doc_id not in {p.doc_id for p in matched}]
    hypothesised = retriever.sections_for(named, MATCHABLE_SECTIONS) if named else []

    shortlist = matched + hypothesised
    if not shortlist:
        return []

    discriminators = retriever.sections_for(
        list(dict.fromkeys(passage.doc_id for passage in shortlist)), [DISCRIMINATING_SECTION]
    )

    # Ranked material first, then everything fetched by id, rather than interleaved by
    # score: the fetched sections carry no meaningful score, and the ranking is what
    # tells the reader which candidates similarity actually matched.
    already = {(p.doc_id, p.section) for p in shortlist}
    return shortlist + [p for p in discriminators if (p.doc_id, p.section) not in already]
