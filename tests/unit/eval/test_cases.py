"""Unit tests for the golden-set schema and loader."""

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.cases import CATEGORIES, CasePlant, GoldenCase, corpus_slugs, load_cases

GOLDEN_SET = Path("eval/golden_set")
CORPUS = Path("knowledge/corpus")


def test_the_golden_set_is_large_enough():
    """PLAN.md §16 specifies 25-30 cases."""
    assert 25 <= len(load_cases(GOLDEN_SET)) <= 30


def test_every_category_has_at_least_two_cases():
    """Per-category breakdowns are the point of the category field; a category with
    one case reports a meaningless 0% or 100%."""
    counts = Counter(case.category for case in load_cases(GOLDEN_SET))
    thin = {category: n for category, n in counts.items() if n < 2}
    assert not thin, f"categories with fewer than two cases: {thin}"


def test_an_unknown_case_field_is_rejected_by_name():
    """A mistyped field name (``defualt_answer``) must fail the suite loudly. With
    28 hand-authored cases, a silent fallback to a schema default would quietly
    corrupt a metric nobody re-derives by hand."""
    with pytest.raises(ValidationError, match="defualt_answer"):
        GoldenCase.model_validate(
            {
                "id": "typo-case",
                "category": "watering",
                "plant": {"name": "Test plant"},
                "symptoms": {
                    "overall_vigor": "declining",
                    "symptoms": [
                        {
                            "description": "wilting leaves",
                            "position": "whole_plant",
                            "severity": "monitor",
                        }
                    ],
                },
                "ground_truth": "overwatering",
                "defualt_answer": "not observed",
            }
        )


def test_an_unknown_plant_field_is_rejected_by_name():
    """Same protection on the nested ``CasePlant`` model — a typo such as
    ``speceis`` would otherwise be silently dropped rather than failing the case."""
    with pytest.raises(ValidationError, match="speceis"):
        CasePlant.model_validate({"name": "Test plant", "speceis": "Ficus elastica"})


def test_every_case_parses():
    cases = load_cases(GOLDEN_SET)
    assert cases, "the golden set is empty"
    assert all(isinstance(case, GoldenCase) for case in cases)


def test_case_ids_are_unique():
    ids = [case.id for case in load_cases(GOLDEN_SET)]
    assert len(ids) == len(set(ids))


def test_every_ground_truth_resolves_to_a_corpus_document():
    """A case naming a disorder the corpus does not contain would score zero at
    runtime for a reason that has nothing to do with agent quality (spec §6)."""
    slugs = corpus_slugs(CORPUS)
    unknown = {
        case.id: case.ground_truth
        for case in load_cases(GOLDEN_SET)
        if case.ground_truth not in slugs
    }
    assert not unknown, f"ground_truth not in corpus: {unknown}"


def test_every_alternative_resolves_to_a_corpus_document():
    slugs = corpus_slugs(CORPUS)
    unknown = {
        case.id: sorted(set(case.also_acceptable) - slugs)
        for case in load_cases(GOLDEN_SET)
        if set(case.also_acceptable) - slugs
    }
    assert not unknown, f"also_acceptable not in corpus: {unknown}"


def test_ground_truth_is_not_repeated_in_alternatives():
    offenders = [
        case.id for case in load_cases(GOLDEN_SET) if case.ground_truth in case.also_acceptable
    ]
    assert not offenders


def test_every_category_is_from_the_fixed_vocabulary():
    for case in load_cases(GOLDEN_SET):
        assert case.category in CATEGORIES


def test_a_malformed_case_names_the_file(tmp_path):
    """Fail at the suite, not at runtime — the philosophy test_corpus_coverage uses."""
    bad = tmp_path / "broken.yaml"
    bad.write_text("id: broken\ncategory: watering\n", encoding="utf-8")

    with pytest.raises(ValueError, match="broken.yaml"):
        load_cases(tmp_path)


def test_an_empty_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no golden cases"):
        load_cases(tmp_path)
