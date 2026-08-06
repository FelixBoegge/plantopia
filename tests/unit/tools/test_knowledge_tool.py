"""Tests for symptom-driven query construction and knowledge search."""

from agent.schemas import Severity, Symptom, SymptomPosition, SymptomSet
from tools.knowledge import build_symptom_queries, search_plant_knowledge


def _symptoms() -> SymptomSet:
    return SymptomSet(
        symptoms=[
            Symptom(
                description="Yellowing leaves",
                position=SymptomPosition.LOWER_LEAVES,
                severity=Severity.ACT_THIS_WEEK,
            ),
            Symptom(
                description="Fine webbing",
                position=SymptomPosition.STEM,
                severity=Severity.ACT_TODAY,
            ),
        ],
        soil_condition="wet",
        overall_vigor="declining",
    )


def test_one_query_per_symptom_plus_a_combined_query():
    queries = build_symptom_queries(_symptoms(), species="Basil")
    assert len(queries) == 3


def test_each_symptom_query_includes_its_position():
    queries = build_symptom_queries(_symptoms(), species=None)
    assert any("lower_leaves" in q or "lower leaves" in q for q in queries)


def test_species_is_included_when_known():
    queries = build_symptom_queries(_symptoms(), species="Basil")
    assert any("Basil" in q for q in queries)


def test_queries_are_built_without_a_species():
    queries = build_symptom_queries(_symptoms(), species=None)
    assert all(isinstance(q, str) and q.strip() for q in queries)


def test_search_returns_ranked_passages(chroma_retriever):
    queries = build_symptom_queries(_symptoms(), species=None)
    passages = search_plant_knowledge(chroma_retriever, queries, k=4)
    assert len(passages) <= 4
    assert [p.score for p in passages] == sorted((p.score for p in passages), reverse=True)


def test_search_with_no_queries_returns_empty(chroma_retriever):
    assert search_plant_knowledge(chroma_retriever, [], k=4) == []
