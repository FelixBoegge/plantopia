"""Tests for the observation repository."""

from uuid import UUID

import pytest

from core.ids import new_id
from data.models import Observation
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository


@pytest.fixture
def plant_id(db, owner, now) -> UUID:
    return PlantRepository(db).create(
        owner,
        name="Basil",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )


def test_photo_refs_round_trip_as_a_list(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    obs_id = repo.create(
        owner,
        plant_id=plant_id,
        kind="initial",
        photo_refs=["img-1", "img-2", "img-3"],
        user_notes="leaves drooping",
        now=now(),
    )
    observation = repo.get(owner, obs_id)
    assert observation is not None
    assert observation.photo_refs == ["img-1", "img-2", "img-3"]
    assert observation.user_notes == "leaves drooping"
    assert observation.kind == "initial"


def test_empty_photo_refs_round_trip(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    obs_id = repo.create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    assert repo.get(owner, obs_id).photo_refs == []


def test_list_for_plant_is_chronological(db, owner, now, plant_id):
    repo = ObservationRepository(db)
    first = repo.create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=now()
    )
    second = repo.create(
        owner, plant_id=plant_id, kind="recheck", photo_refs=[], user_notes=None, now=now()
    )
    assert [o.id for o in repo.list_for_plant(owner, plant_id)] == [first, second]


def test_get_returns_none_for_unknown_id(db, owner):
    assert ObservationRepository(db).get(owner, new_id()) is None


class TestWhatThePhotographsSaid:
    """Recorded on the observation, separately from when it was uploaded.

    Null in all three means no photograph declared anything, which is most of them and is
    not a failure — and is what every row written before these columns existed says about
    itself, truthfully, with nothing to backfill from.
    """

    def test_a_capture_date_and_a_coarse_position_round_trip(self, db, owner, now):
        from datetime import UTC, datetime

        from data.repositories.plants import PlantRepository

        plant_id = PlantRepository(db).create(
            owner,
            name="Test plant",
            species=None,
            species_confidence=None,
            location_kind="outdoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )
        taken = datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC)

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
            captured_at=taken,
            latitude=54.5,
            longitude=3.2,
        )

        row = db.get(Observation, observation_id)
        assert row.captured_at == taken
        assert (row.latitude, row.longitude) == (54.5, 3.2)
        assert row.created_at != taken, (
            "the upload moment and the capture moment are different facts"
        )

    def test_an_observation_that_knew_neither(self, db, owner, now):
        from data.repositories.plants import PlantRepository

        plant_id = PlantRepository(db).create(
            owner,
            name="Test plant",
            species=None,
            species_confidence=None,
            location_kind="indoor",
            location_text=None,
            photo_ref=None,
            now=now(),
        )

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
        )

        row = db.get(Observation, observation_id)
        assert row.captured_at is None
        assert row.latitude is None
        assert row.longitude is None


class TestTheWeatherAnObservationWasMadeAgainst:
    """A diagnosis's evidence should be recoverable.

    "Why did it say frost damage?" has an answer only while the frost is still on the
    record. The five aggregate numbers this replaced went into a prompt and were never kept,
    so every past diagnosis's weather is gone.
    """

    def _series(self, days: int = 3):
        from datetime import date, timedelta

        from agent.schemas import WeatherDay
        from tools.weather import summarise

        return summarise(
            [
                WeatherDay(
                    on=date(2026, 8, 10) + timedelta(days=i),
                    min_temp_c=-1.5 + i,
                    max_temp_c=18.0 + i,
                    precip_mm=0.5 * i,
                )
                for i in range(days)
            ]
        )

    def test_a_series_round_trips_day_for_day(self, db, owner, now, plant_id):
        """Day for day, not merely "a series was stored". A round trip that kept the
        aggregates and lost the dates would pass a shallower assertion and lose the whole
        point of the change."""
        summary = self._series()

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
            weather=summary,
        )

        read = ObservationRepository(db).get(owner, observation_id)
        assert read is not None
        assert read.weather is not None
        assert read.weather.days == summary.days
        assert read.weather == summary

    def test_the_forecast_round_trips_too(self, db, owner, now, plant_id):
        from datetime import date

        from agent.schemas import WeatherDay

        summary = self._series()
        summary.forecast = [
            WeatherDay(on=date(2026, 9, 1), min_temp_c=8.0, max_temp_c=19.0, precip_mm=2.0)
        ]

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
            weather=summary,
        )

        read = ObservationRepository(db).get(owner, observation_id)
        assert read is not None
        assert read.weather is not None
        assert read.weather.forecast == summary.forecast

    def test_an_observation_from_before_this_reports_no_weather(self, db, owner, now, plant_id):
        """`None`, not an empty window.

        An empty window claims the weather was looked up and found to be nothing at all.
        Every row written before this column existed, and every indoor plant, means the
        other thing: nothing was looked up. Reporting them the same way would make a
        diagnosis that ignored the weather indistinguishable from one made in a place where
        nothing happened.
        """
        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
        )

        read = ObservationRepository(db).get(owner, observation_id)
        assert read is not None
        assert read.weather is None
        assert read.weather != []

    def test_the_column_itself_is_null_rather_than_the_string_null(self, db, owner, now, plant_id):
        """`json.dumps(None)` is the four characters `null`, which reads back as a value."""
        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=plant_id,
            kind="initial",
            photo_refs=["img-1"],
            user_notes=None,
            now=now(),
        )

        assert db.get(Observation, observation_id).weather_json is None
