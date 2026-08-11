"""Smoke tests for the My Plants page."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui

_MY_PLANTS_PAGE = Path(__file__).resolve().parent.parent.parent / "ui" / "pages" / "my_plants.py"


@pytest.fixture
def app(monkeypatch, db, now):
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
