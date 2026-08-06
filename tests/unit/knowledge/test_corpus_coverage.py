"""Validates that the corpus is complete and well-formed.

This test is the specification for the corpus. Add a document, and this tells you
whether it is usable before the retriever ever sees it.
"""

from pathlib import Path

import pytest

from knowledge.ingest import REQUIRED_SECTIONS, load_corpus, parse_document

CORPUS = Path("knowledge/corpus")

REQUIRED_IDS = {
    "water-and-root": {
        "root-rot", "overwatering", "underwatering", "poor-drainage",
        "transplant-shock", "pot-bound",
    },
    "nutrient": {
        "nitrogen-deficiency", "phosphorus-deficiency", "potassium-deficiency",
        "iron-deficiency", "magnesium-deficiency", "calcium-deficiency",
        "fertiliser-burn", "salt-buildup",
    },
    "light-and-environment": {
        "insufficient-light", "sunscald", "low-humidity", "cold-draught",
        "frost-damage", "heat-stress", "chemical-damage",
    },
    "pests": {
        "spider-mites", "thrips", "aphids", "mealybugs", "scale-insects",
        "fungus-gnats", "whitefly", "caterpillars", "slugs-and-snails", "vine-weevil",
    },
    "disease": {
        "powdery-mildew", "botrytis", "bacterial-leaf-spot", "fungal-leaf-spot",
        "rust", "anthracnose", "sooty-mould", "damping-off",
    },
    "other": {"natural-senescence", "physical-damage", "dormancy", "etiolation"},
}

ALL_REQUIRED_IDS = set().union(*REQUIRED_IDS.values())


@pytest.fixture(scope="module")
def chunks():
    return load_corpus(CORPUS)


def test_every_required_disorder_is_documented(chunks):
    present = {c.doc_id for c in chunks}
    assert ALL_REQUIRED_IDS <= present, f"missing: {sorted(ALL_REQUIRED_IDS - present)}"


def test_every_document_parses(chunks):
    assert chunks


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_document_has_every_required_section(path):
    sections = {c.section for c in parse_document(path)}
    assert REQUIRED_SECTIONS <= sections


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_document_id_matches_its_filename(path):
    assert parse_document(path)[0].doc_id == path.stem


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_document_category_is_recognised(path):
    assert parse_document(path)[0].category in REQUIRED_IDS


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_document_severity_is_valid(path):
    assert parse_document(path)[0].severity in {"monitor", "act_this_week", "act_today"}


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_lookalike_section_is_substantive(path):
    """The look-alike section is what makes differential diagnosis possible."""
    chunk = next(
        c for c in parse_document(path)
        if c.section == "Look-alikes and how to tell them apart"
    )
    assert len(chunk.text) >= 150, "too thin to discriminate between candidates"


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_confirming_test_is_actionable(path):
    chunk = next(
        c for c in parse_document(path)
        if c.section == "Confirming test the user can perform"
    )
    assert len(chunk.text) >= 80


def test_pest_and_disease_documents_are_marked_transmissible(chunks):
    """A pest or pathogen that spreads must be flagged, or contagion triage misses it."""
    non_transmissible_pests = {
        c.doc_id for c in chunks if c.category in {"pests", "disease"} and not c.transmissible
    }
    assert non_transmissible_pests <= {"damping-off", "sooty-mould"}


def test_environmental_disorders_are_not_transmissible(chunks):
    wrongly_flagged = {
        c.doc_id
        for c in chunks
        if c.category in {"nutrient", "light-and-environment", "water-and-root"}
        and c.transmissible
    }
    assert wrongly_flagged == set()
