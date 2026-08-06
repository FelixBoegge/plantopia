"""Validates that the corpus is complete and well-formed.

This test is the specification for the corpus. Add a document, and this tells you
whether it is usable before the retriever ever sees it.
"""

import re
from pathlib import Path

import pytest

from knowledge.ingest import REQUIRED_SECTIONS, load_corpus, parse_document

CORPUS = Path("knowledge/corpus")

# PLAN §13.5: chemical treatment is "least-toxic option only, and never a specific
# dose of a restricted product; the user is directed to the product label". This is
# a safety property, not a style preference, so it gets a structural regression
# guard rather than resting on a prompt sentence and a one-time manual corpus read.
#
# Matches: a number immediately followed by a volume/mass/concentration unit
# (ml, l, g, kg, tsp, tbsp, %, ppm), or the ratio phrase "per litre"/"per gallon".
# Deliberately does NOT match spelled-out quantities ("top three centimetres"),
# lengths ("3 cm"), temperatures ("18-30°C"), or day/week counts ("every three
# days") — none of those are chemical doses.
DOSE_PATTERN = re.compile(
    r"""
    \b\d+(?:\.\d+)?\s?%                                # 1%, 0.5 %
    | \b\d+(?:\.\d+)?\s?(?:ml|l|g|kg|tsp|tbsp|ppm)\b    # 5ml, 2 tbsp, 300 ppm
    | \bper\s+(?:litre|liter|gallon)\b                  # per litre / per gallon
    """,
    re.IGNORECASE | re.VERBOSE,
)

REQUIRED_IDS = {
    "water-and-root": {
        "root-rot",
        "overwatering",
        "underwatering",
        "poor-drainage",
        "transplant-shock",
        "pot-bound",
    },
    "nutrient": {
        "nitrogen-deficiency",
        "phosphorus-deficiency",
        "potassium-deficiency",
        "iron-deficiency",
        "magnesium-deficiency",
        "calcium-deficiency",
        "fertiliser-burn",
        "salt-buildup",
    },
    "light-and-environment": {
        "insufficient-light",
        "sunscald",
        "low-humidity",
        "cold-draught",
        "frost-damage",
        "heat-stress",
        "chemical-damage",
    },
    "pests": {
        "spider-mites",
        "thrips",
        "aphids",
        "mealybugs",
        "scale-insects",
        "fungus-gnats",
        "whitefly",
        "caterpillars",
        "slugs-and-snails",
        "vine-weevil",
    },
    "disease": {
        "powdery-mildew",
        "botrytis",
        "bacterial-leaf-spot",
        "fungal-leaf-spot",
        "rust",
        "anthracnose",
        "sooty-mould",
        "damping-off",
    },
    "other": {"natural-senescence", "physical-damage", "dormancy", "etiolation"},
}

ALL_REQUIRED_IDS = set().union(*REQUIRED_IDS.values())


@pytest.fixture(scope="module")
def chunks():
    return load_corpus(CORPUS)


def test_every_required_disorder_is_documented(chunks):
    present = {c.doc_id for c in chunks}
    assert present >= ALL_REQUIRED_IDS, f"missing: {sorted(ALL_REQUIRED_IDS - present)}"


def test_every_document_parses(chunks):
    assert chunks


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_document_has_every_required_section(path):
    sections = {c.section for c in parse_document(path)}
    assert sections >= REQUIRED_SECTIONS


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
        c for c in parse_document(path) if c.section == "Look-alikes and how to tell them apart"
    )
    assert len(chunk.text) >= 150, "too thin to discriminate between candidates"


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_confirming_test_is_actionable(path):
    chunk = next(
        c for c in parse_document(path) if c.section == "Confirming test the user can perform"
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
        if c.category in {"nutrient", "light-and-environment", "water-and-root"} and c.transmissible
    }
    assert wrongly_flagged == set()


@pytest.mark.parametrize(
    "text",
    [
        "dilute 5ml in one litre of water",
        "mix in 1l of water before spraying",
        "use a 2% solution on the affected leaves",
        "apply at 300 ppm",
        "use 1 tsp per gallon of water",
        "add 2 tbsp of neem oil to the sprayer",
        "work 10 kg of compost into the bed",
    ],
    ids=[
        "ml-volume",
        "l-volume",
        "percent-concentration",
        "ppm-concentration",
        "tsp-per-gallon",
        "tbsp-quantity",
        "kg-quantity",
    ],
)
def test_dose_pattern_flags_dose_shaped_text(text):
    assert DOSE_PATTERN.search(text), f"expected a dose match in {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "keep the top three centimetres of soil moist",
        "let the top 3 cm of the pot dry out between waterings",
        "keep night temperatures between 18 and 30 degrees C",
        "repeat every three days for two weeks to break the life cycle",
        "wait 10 days before repeating the treatment",
        "reduce watering frequency by half",
        "isolate the plant for at least 7 days",
    ],
    ids=[
        "spelled-out-length",
        "length-in-cm",
        "temperature-range",
        "spelled-out-day-count",
        "numeric-day-count",
        "no-numbers",
        "day-count-with-unit-like-suffix",
    ],
)
def test_dose_pattern_does_not_flag_legitimate_corpus_prose(text):
    assert not DOSE_PATTERN.search(text), f"unexpected dose match in {text!r}"


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.md")), ids=lambda p: p.stem)
def test_treatment_section_never_states_a_specific_dose(path):
    """The treatment section may name a least-toxic product but must never give a
    dose for it — the user is directed to the product label instead (PLAN §13.5).
    """
    chunk = next(c for c in parse_document(path) if c.section == "Treatment, least-invasive first")
    match = DOSE_PATTERN.search(chunk.text)
    assert match is None, f"{path.stem}: dose-shaped text found: {match.group(0)!r}"
