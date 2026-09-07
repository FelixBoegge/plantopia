"""The plant endpoints."""

from core.ids import new_id
from tests.api.conftest import NOW

BASE = "/api/v1/plants"


def test_listing_returns_the_owners_plants(client, seeded):
    response = client.get(BASE)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["plant"]["name"] == "Kitchen basil"
    assert body[0]["latest_diagnosis"]["candidates"][0]["disorder_id"] == "overwatering"
    assert body[0]["pending_step_count"] == 1


def test_an_owner_with_no_plants_gets_an_empty_list(client):
    """Empty rather than an error: having no plants is a normal state, not a failure."""
    response = client.get(BASE)

    assert response.status_code == 200
    assert response.json() == []


def test_reading_one_plant_returns_its_history(client, seeded):
    response = client.get(f"{BASE}/{seeded['plant_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["plant"]["species"] == "Ocimum basilicum"
    assert len(body["observations"]) == 1
    assert len(body["diagnoses"]) == 1
    assert len(body["roadmap_steps"]) == 1
    assert body["feedback_due"] is False


def test_an_unknown_plant_is_not_found(client):
    response = client.get(f"{BASE}/{new_id()}")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not-found")


def test_an_identifier_that_is_not_an_identifier_is_rejected(client):
    """Malformed input is a client error, and says nothing about what exists."""
    response = client.get(f"{BASE}/not-a-uuid")

    assert response.status_code == 422
    assert "exist" not in response.text.lower()


def test_renaming_changes_the_name_and_not_the_species(client, seeded):
    response = client.patch(f"{BASE}/{seeded['plant_id']}", json={"name": "Windowsill basil"})

    assert response.status_code == 200
    body = response.json()
    assert body["plant"]["name"] == "Windowsill basil"
    assert body["plant"]["species"] == "Ocimum basilicum"


def test_a_blank_name_is_refused(client, seeded):
    """A plant with an empty name renders as an unlabelled card with no way back."""
    response = client.patch(f"{BASE}/{seeded['plant_id']}", json={"name": "   "})

    assert response.status_code in (400, 422)
    assert client.get(f"{BASE}/{seeded['plant_id']}").json()["plant"]["name"] == "Kitchen basil"


def test_deleting_removes_the_plant_and_its_history(client, seeded):
    assert client.delete(f"{BASE}/{seeded['plant_id']}").status_code == 204

    assert client.get(f"{BASE}/{seeded['plant_id']}").status_code == 404
    assert client.get(BASE).json() == []


def test_deleting_removes_the_photographs_too(client, seeded):
    """Nothing else relates the bytes back to the plant: a photograph is owned by a
    person, because an upload exists before the plant it documents does."""
    photo = f"/api/v1/photos/{seeded['photo_key']}"
    assert client.get(photo).status_code == 200

    client.delete(f"{BASE}/{seeded['plant_id']}")

    assert client.get(photo).status_code == 404


def test_deleting_something_that_is_not_there_is_not_found(client):
    assert client.delete(f"{BASE}/{new_id()}").status_code == 404


def test_the_response_carries_only_the_documented_fields(client, seeded):
    """Response schemas are written rather than inferred, so a storage column added later
    cannot appear here by accident."""
    plant = client.get(f"{BASE}/{seeded['plant_id']}").json()["plant"]

    assert set(plant) == {
        "id",
        "name",
        "species",
        "species_scientific",
        "species_confidence",
        "location_kind",
        "location_text",
        "photo_ref",
        "created_at",
    }


class TestWhatAnObservationCarriesOverTheWire:
    """The weather was on the record and the converter dropped it; the capture date and the
    position stopped one layer earlier. Nothing read any of them, so nothing noticed."""

    def _observation(self, db, owner, seeded, **fields):
        from data.repositories.observations import ObservationRepository

        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=seeded["plant_id"],
            kind="recheck",
            photo_refs=["img-1"],
            user_notes=None,
            now=NOW,
            **fields,
        )
        db.commit()
        return observation_id

    def _read(self, client, seeded, observation_id):
        body = client.get(f"/api/v1/plants/{seeded['plant_id']}").json()
        return next(o for o in body["observations"] if o["id"] == str(observation_id))

    def test_the_capture_date_and_position_arrive(self, client, db, owner, seeded):
        from datetime import UTC, datetime

        observation_id = self._observation(
            db,
            owner,
            seeded,
            captured_at=datetime(2026, 8, 10, 10, 50, 49, tzinfo=UTC),
            latitude=50.1,
            longitude=8.7,
        )

        out = self._read(client, seeded, observation_id)

        assert out["captured_at"].startswith("2026-08-10")
        assert (out["latitude"], out["longitude"]) == (50.1, 8.7)

    def test_the_weather_arrives(self, client, db, owner, seeded):
        """Reachable until now only through a diagnosis made from this observation, which
        fails for a re-check whose run was cancelled."""
        from datetime import date, timedelta

        from agent.schemas import WeatherDay
        from tools.weather import summarise

        summary = summarise(
            [
                WeatherDay(
                    on=date(2026, 8, 10) + timedelta(days=i),
                    min_temp_c=-1.0 if i == 2 else 12.0,
                    max_temp_c=19.0,
                    precip_mm=0.0,
                )
                for i in range(4)
            ]
        )
        observation_id = self._observation(db, owner, seeded, weather=summary)

        out = self._read(client, seeded, observation_id)

        assert out["weather"] is not None
        assert [day["on"] for day in out["weather"]["days"]][0] == "2026-08-10"
        assert out["weather"]["frost_days"] == 1

    def test_an_observation_that_knows_none_of_it_says_so(self, client, db, owner, seeded):
        """Null rather than absent-meaning-zero. Every observation recorded before those
        columns existed is in exactly this position."""
        observation_id = self._observation(db, owner, seeded)

        out = self._read(client, seeded, observation_id)

        assert out["captured_at"] is None
        assert out["latitude"] is None
        assert out["longitude"] is None
        assert out["weather"] is None
