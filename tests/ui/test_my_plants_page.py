"""Smoke tests for the My Plants page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

_MY_PLANTS_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "my_plants.py"


@pytest.fixture
def app(monkeypatch, db, now):
    """The My Plants page with every bootstrap accessor it touches swapped for a fake
    wired to the in-memory test database. Left unmocked, it would fall through to the
    real ``@st.cache_resource``-cached service and open a connection to the actual
    project database file (spec risk flagged in Task 9's review): every test in this
    file would then run ``apply_schema`` (which commits) against production data on
    every run, purely as a side effect of rendering the page.
    """
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.feedback import FeedbackRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from services.plant_service import PlantService

    service = PlantService(
        plants=PlantRepository(db),
        observations=ObservationRepository(db),
        diagnoses=DiagnosisRepository(db),
        roadmap=RoadmapRepository(db),
        feedback=FeedbackRepository(db),
        now=now,
    )
    monkeypatch.setattr("ui.bootstrap.get_plant_service", lambda: service)

    return AppTest.from_file(str(_MY_PLANTS_PAGE), default_timeout=30)


def test_page_renders_without_exception(app):
    app.run()
    assert not app.exception


def test_empty_state_invites_a_first_diagnosis(app):
    app.run()
    assert any("Diagnose" in b.label for b in app.button)


def test_a_plant_appears_as_a_card(app, db, now):
    from data.repositories.plants import PlantRepository

    PlantRepository(db).create(
        name="Kitchen basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    app.run()
    assert any("Kitchen basil" in m.value for m in app.markdown)


def test_a_diagnosed_plant_shows_its_primary_candidate_and_pending_steps(app, sample_plant):
    """``sample_plant`` (tests/conftest.py) is an unhealthy diagnosis — top candidate
    Overwatering at 70% — with two roadmap steps, one done and one still pending.
    Exercises the unhealthy branch, the per-card pending count, and the aggregate
    "due across your plants" caption in one pass.

    The card's own lines are markdown, not captions: they share half a card with the
    photograph, where caption-sized text was too small to read. The aggregate line
    above the grid is still a caption — it is genuinely secondary.
    """
    app.run()
    assert not app.exception
    assert any("Overwatering" in m.value for m in app.markdown)
    assert any("1 step(s) pending" in m.value for m in app.markdown)
    assert any("step(s) due across your plants" in c.value for c in app.caption)


def test_a_healthy_plant_shows_the_healthy_verdict(app, db, now):
    """A healthy plant is a distinct, first-class outcome (PLAN §14), not the absence
    of a diagnosis — this must render its own verdict rather than falling through to
    "No diagnosis yet"."""
    from agent.schemas import Differential
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        name="Healthy fern",
        species="Fern",
        species_confidence=0.8,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    observation_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    DiagnosisRepository(db).create(
        observation_id=observation_id,
        plant_id=plant_id,
        differential=Differential(
            is_healthy=True, candidates=[], reasoning="No symptoms of concern."
        ),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
    )
    app.run()
    assert not app.exception
    assert any("Healthy" in m.value for m in app.markdown)


def test_view_button_selects_the_plant_before_navigating(app, sample_plant):
    """Clicking "View" must record which plant was chosen (consumed by the Plant
    detail page, Task 18) before it tries to navigate there.

    The navigation itself raises under ``AppTest`` here: this page isn't registered
    in app.py's page set yet (that wiring is Task 23), so Streamlit's
    ``switch_page`` cannot resolve "ui/pages/plant_detail.py" relative to a
    ``pages/`` directory. Asserting the exception names that exact target confirms
    the button is wired correctly today, not merely that it fails silently.
    """
    app.run()
    view_button = next(b for b in app.button if b.label == "View")
    view_button.click().run()
    assert app.session_state["selected_plant_id"] == sample_plant
    assert "ui/pages/plant_detail.py" in str(app.exception[0])


def test_diagnose_button_attempts_to_navigate_to_the_diagnose_page(app):
    """Empty-state CTA. Same navigation caveat as the "View" button above — the
    target page is real, but unreachable from a page loaded standalone until app.py
    registers it (Task 23)."""
    app.run()
    diagnose_button = next(b for b in app.button if b.label == "Diagnose a plant")
    diagnose_button.click().run()
    assert "ui/pages/diagnose.py" in str(app.exception[0])


def test_add_a_plant_button_attempts_to_navigate_to_the_diagnose_page(app, sample_plant):
    """Same button target as the empty-state CTA, reachable once at least one plant
    exists."""
    app.run()
    add_button = next(b for b in app.button if b.label == "Add a plant")
    add_button.click().run()
    assert "ui/pages/diagnose.py" in str(app.exception[0])


def test_the_card_that_overflows_a_row_starts_a_new_one(app, db, now):
    """The grid builds one ``st.columns()`` call per row.

    The earlier shape called ``st.columns`` once and indexed it by ``index % 3``,
    which does not wrap: the fourth card lands *underneath* the first, inside the
    same column, so cards no longer line up in rows at all. Asserted as a
    difference rather than a total so it stays true of whatever else the page grows:
    a new row costs three columns plus the arriving card's own photo/details split,
    where the broken shape would cost only the split.
    """
    from data.repositories.plants import PlantRepository

    cards_per_row, columns_per_card = 3, 2
    repo = PlantRepository(db)

    def add(name: str) -> None:
        repo.create(
            name=name,
            species="Basil",
            species_confidence=0.9,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )

    for name in ("one", "two", "three"):
        add(name)
    app.run()
    filled_row = len(app.columns)

    add("four")
    app.run()

    assert len(app.columns) - filled_row == cards_per_row + columns_per_card
