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


def search_plant_knowledge(
    retriever: Retriever,
    queries: Sequence[str],
    k: int = 6,
) -> list[Passage]:
    """Search the curated corpus. Returns an empty list when given no queries."""
    if not queries:
        return []
    return retriever.search(queries, k=k)
