"""Tests for symptom-driven query construction and knowledge search."""

from agent.schemas import Severity, Symptom, SymptomPosition, SymptomSet
from tools.knowledge import (
    DISCRIMINATING_SECTION,
    MATCHABLE_SECTIONS,
    build_symptom_queries,
    search_plant_knowledge,
)


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


def test_k_bounds_the_candidates_not_the_passage_count(chroma_retriever):
    """``k`` counts disorders shortlisted, not passages returned.

    Each shortlisted disorder also contributes its look-alikes section, so the total
    runs to at most twice ``k`` — fewer when a document lacks that section.
    """
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4)

    assert len({p.doc_id for p in passages}) <= 4
    assert len(passages) <= 8


def test_the_shortlist_is_ranked_and_comes_first(chroma_retriever):
    """The searched passages stay in score order at the front. The appended sections
    were fetched by id and carry no score, so interleaving them by score would bury
    the ranking that tells a reader which candidates actually matched."""
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4)
    ranked = [p for p in passages if p.section != DISCRIMINATING_SECTION]

    assert passages[: len(ranked)] == ranked
    assert [p.score for p in ranked] == sorted((p.score for p in ranked), reverse=True)


def test_one_passage_per_disorder_in_the_shortlist(chroma_retriever):
    """Sections of one document used to compete with each other for slots, letting a
    broadly-worded distractor hold three of six while the right answer held one."""
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4)
    ranked = [p for p in passages if p.section != DISCRIMINATING_SECTION]

    assert len({p.doc_id for p in ranked}) == len(ranked)


def test_every_shortlisted_disorder_contributes_its_look_alikes(chroma_retriever):
    """The section that says how to tell this disorder from the ones it resembles —
    the material the diagnosis was missing — must arrive for every candidate, not
    only for those whose look-alikes section happened to rank."""
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4)
    shortlisted = {p.doc_id for p in passages if p.section != DISCRIMINATING_SECTION}
    with_discriminator = {p.doc_id for p in passages if p.section == DISCRIMINATING_SECTION}

    assert shortlisted, "the fixture corpus should match these symptoms somehow"
    assert shortlisted == with_discriminator


def test_no_passage_is_returned_twice(chroma_retriever):
    """A look-alikes section that ranked on its own must not be appended again."""
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4)

    keys = [(p.doc_id, p.section) for p in passages]
    assert len(keys) == len(set(keys))


def test_search_with_no_queries_returns_empty(chroma_retriever):
    assert search_plant_knowledge(chroma_retriever, [], k=4) == []


def test_only_descriptive_sections_are_allowed_to_match(chroma_retriever):
    """A look-alikes section describes the disorders it rules *out*, so it attracts
    queries about them: measured on a nitrogen case, phosphorus-deficiency's
    look-alikes section outscored nitrogen-deficiency's own symptoms. Only sections
    that describe the disorder itself may earn a document its place on the shortlist.
    """
    calls: list[tuple[int, list[str] | None]] = []

    class _Recorder:
        def search(self, queries, k, *, sections=None):
            calls.append((k, list(sections) if sections else None))
            return chroma_retriever.search(queries, k, sections=sections)

        def sections_for(self, doc_ids, sections):
            return chroma_retriever.sections_for(doc_ids, sections)

    queries = build_symptom_queries(_symptoms(), species=None)
    passages = search_plant_knowledge(_Recorder(), queries, k=4)

    assert calls == [(4, list(MATCHABLE_SECTIONS))]
    ranked = [p for p in passages if p.section != DISCRIMINATING_SECTION]
    assert {p.section for p in ranked} <= set(MATCHABLE_SECTIONS)


def test_hypothesised_documents_arrive_regardless_of_rank(chroma_retriever):
    """The whole point of naming a disorder: rank stops mattering.

    Measured on the golden set, the correct document sat at 16th, 17th and 21st of 43
    for three nutrient cases — beyond any k a prompt can carry. A named document is one
    lookup away.
    """
    queries = build_symptom_queries(_symptoms(), species=None)

    passages = search_plant_knowledge(
        chroma_retriever, queries, k=4, hypotheses=["potassium-deficiency"]
    )

    assert "potassium-deficiency" in {p.doc_id for p in passages}


def test_a_hypothesised_document_brings_its_descriptive_sections(chroma_retriever):
    """A named candidate must not be argued about on thinner evidence than one
    similarity happened to find, or the differential is biased towards whatever ranked."""
    passages = search_plant_knowledge(
        chroma_retriever, [], k=4, hypotheses=["potassium-deficiency"]
    )

    sections = {p.section for p in passages if p.doc_id == "potassium-deficiency"}
    assert set(MATCHABLE_SECTIONS) <= sections
    assert DISCRIMINATING_SECTION in sections


def test_a_hypothesis_that_similarity_also_found_is_not_duplicated(chroma_retriever):
    queries = build_symptom_queries(_symptoms(), species=None)
    matched = search_plant_knowledge(chroma_retriever, queries, k=4)
    found_anyway = next(p.doc_id for p in matched)

    passages = search_plant_knowledge(chroma_retriever, queries, k=4, hypotheses=[found_anyway])

    keys = [(p.doc_id, p.section) for p in passages]
    assert len(keys) == len(set(keys))


def test_hypotheses_alone_are_enough_to_retrieve(chroma_retriever):
    """Symptom extraction can fail while a hypothesis survives — the node is skipped in
    that case today, but the retrieval path must not depend on queries existing."""
    passages = search_plant_knowledge(chroma_retriever, [], k=4, hypotheses=["root-rot"])

    assert {p.doc_id for p in passages} == {"root-rot"}


def test_neither_queries_nor_hypotheses_returns_nothing(chroma_retriever):
    assert search_plant_knowledge(chroma_retriever, [], k=4, hypotheses=[]) == []
