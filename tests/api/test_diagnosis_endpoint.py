"""Fetching one diagnosis.

The run reports an identifier when it completes. If that identifier cannot be resolved, the
client has been handed a receipt rather than a result.
"""

from agent.schemas import Passage
from core.ids import new_id
from data.repositories.runs import RunRepository
from runs import steps
from tests.accounts import NOW
from tests.api.conftest import _differential
from tests.runs import make_run


def _with_activity(db, owner, seeded, payload):
    """A finished run that produced the seeded diagnosis, with one step recorded."""
    run = make_run(db, owner, plant_id=seeded["plant_id"], diagnosis_id=seeded["diagnosis_id"])
    db.flush()
    RunRepository(db).append_event(run.id, kind=steps.STEP, payload=payload, now=NOW)
    db.commit()
    return run


def test_a_diagnosis_can_be_fetched_by_its_identifier(client, seeded):
    response = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}")

    assert response.status_code == 200
    assert response.json()["diagnosis"]["id"] == str(seeded["diagnosis_id"])


def test_it_carries_the_differential(client, seeded):
    """Every candidate, in order, with what argues for and against it — not a verdict."""
    body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

    assert body["diagnosis"]["candidates"]
    assert body["diagnosis"]["reasoning"]


def test_it_carries_the_plan_that_diagnosis_produced(client, seeded):
    """Read together on every screen that shows either, so they travel together rather than
    as two requests a client has to sequence."""
    body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

    assert body["roadmap_steps"]


def test_it_carries_only_that_diagnosis_plan(client, db, owner, seeded):
    """A plant with two diagnoses has two plans, and showing the wrong one would be showing
    somebody last week's advice."""
    body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

    assert {step["diagnosis_id"] for step in body["roadmap_steps"]} == {str(seeded["diagnosis_id"])}


def test_an_unknown_diagnosis_is_absent(client):
    assert client.get(f"/api/v1/diagnoses/{new_id()}").status_code == 404


def test_it_says_where_the_species_came_from(client, seeded):
    """The two fields that tell a bad identification apart from bad reasoning about a good
    one. A client that cannot read them cannot show anybody why to doubt a diagnosis."""
    body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

    assert "species_method" in body["diagnosis"]
    assert "species_confirmed" in body["diagnosis"]


def test_a_diagnosis_with_no_recorded_provenance_says_so(client, seeded):
    """Not a guess and not an omission: null, meaning nothing recorded it. Every diagnosis
    made before this existed is in exactly this position."""
    body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

    assert body["diagnosis"]["species_method"] is None
    assert body["diagnosis"]["species_confirmed"] is False


class TestTheWeatherItWasReasonedAgainst:
    """Storing a series nothing reads is what `M40` records as a mistake. This is the read."""

    def _stored(self, db, owner, seeded):
        from datetime import UTC, date, datetime, timedelta

        from agent.schemas import WeatherDay
        from data.repositories.diagnoses import DiagnosisRepository
        from data.repositories.observations import ObservationRepository
        from tools.weather import summarise

        summary = summarise(
            [
                WeatherDay(
                    on=date(2026, 8, 10) + timedelta(days=i),
                    min_temp_c=-2.0,
                    max_temp_c=14.0,
                    precip_mm=0.0,
                )
                for i in range(3)
            ]
        )
        observation_id = ObservationRepository(db).create(
            owner,
            plant_id=seeded["plant_id"],
            kind="recheck",
            photo_refs=["img-1"],
            user_notes=None,
            now=datetime(2026, 8, 13, tzinfo=UTC),
            weather=summary,
        )
        diagnosis_id = DiagnosisRepository(db).create(
            owner,
            observation_id=observation_id,
            plant_id=seeded["plant_id"],
            differential=_a_differential(db, owner, seeded),
            contagion=None,
            retrieved=[],
            model="test-model",
            now=datetime(2026, 8, 13, tzinfo=UTC),
        )
        db.commit()
        return diagnosis_id

    def test_the_series_comes_back_day_by_day(self, client, db, owner, seeded):
        diagnosis_id = self._stored(db, owner, seeded)

        weather = client.get(f"/api/v1/diagnoses/{diagnosis_id}").json()["diagnosis"]["weather"]

        assert weather is not None
        assert [day["on"] for day in weather["days"]] == [
            "2026-08-10",
            "2026-08-11",
            "2026-08-12",
        ]
        assert weather["frost_days"] == 3

    def test_a_diagnosis_with_no_recorded_weather_says_null(self, client, seeded):
        """Not an empty window. An empty window would say the weather was looked up and
        found to be nothing at all — which is a different thing from an indoor plant, a
        failed lookup, or a diagnosis made before any of this was kept."""
        body = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}").json()

        assert body["diagnosis"]["weather"] is None


def _a_differential(db, owner, seeded):
    """The differential already on the seeded diagnosis, reused rather than rebuilt."""
    from data.repositories.diagnoses import DiagnosisRepository

    record = DiagnosisRepository(db).get(owner, seeded["diagnosis_id"])
    assert record is not None
    return record.differential


def test_the_activity_of_a_diagnosis_is_its_steps(client, db, owner, seeded):
    _with_activity(
        db,
        owner,
        seeded,
        {
            "step": "identifying",
            "description": "Identifying the species",
            "calls": "acme/see-1 via OpenRouter, then Pl@ntNet",
            "duration_ms": 4120,
        },
    )

    response = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}/activity")

    assert response.status_code == 200
    [first] = response.json()
    assert first["step"] == "identifying"
    assert first["calls"] == "acme/see-1 via OpenRouter, then Pl@ntNet"
    assert first["duration_ms"] == 4120


def test_a_step_recorded_before_this_existed_still_reads(client, db, owner, seeded):
    """Events already in the database carry neither key. They are replayed on reconnect and
    read here, so both have to stay optional for good."""
    _with_activity(
        db, owner, seeded, {"step": "identifying", "description": "Identifying the species"}
    )

    response = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}/activity")

    assert response.status_code == 200
    assert response.json()[0]["calls"] is None
    assert response.json()[0]["duration_ms"] is None


def test_a_diagnosis_with_no_recorded_activity_is_an_empty_list(client, seeded):
    """Not a 404. The diagnosis is there; nothing was recorded about how it was reached."""
    response = client.get(f"/api/v1/diagnoses/{seeded['diagnosis_id']}/activity")

    assert response.status_code == 200
    assert response.json() == []


def test_the_activity_of_an_unknown_diagnosis_is_absent(client):
    assert client.get(f"/api/v1/diagnoses/{new_id()}/activity").status_code == 404


class TestWhatTheResultShowsAboutItself:
    """The evidence a diagnosis drew on, and what it cost to produce.

    Both were recorded from the first diagnosis ever written and neither reached a client
    (`U23`). `retrieved_refs_json` has always held the consulted passages;
    `diagnoses.cost_usd` and `token_usage_json` have always held the spend.

    The cost is only worth showing as of `U26`, fixed the same day these arrived: until
    then the record carried the finishing pass alone and understated an interrupted
    diagnosis by about 17%.
    """

    @staticmethod
    def _diagnosis(db, owner, seeded, *, retrieved, usage=None, cost=None):
        from data.repositories.diagnoses import DiagnosisRepository

        diagnosis_id = DiagnosisRepository(db).create(
            owner,
            observation_id=seeded["observation_id"],
            plant_id=seeded["plant_id"],
            differential=_differential(),
            contagion=None,
            retrieved=retrieved,
            model="test-model",
            token_usage=usage,
            cost_usd=cost,
            now=NOW,
        )
        db.commit()
        return diagnosis_id

    def test_it_lists_what_it_consulted(self, client, db, owner, seeded, corpus_retriever):
        """Named from the corpus, not from the slug: `botrytis` is "Botrytis (grey mould)"."""
        found = self._diagnosis(
            db,
            owner,
            seeded,
            retrieved=[
                Passage(doc_id="botrytis", section="Symptoms", text="…", score=0.6),
                Passage(doc_id="web:rhs.org.uk", section="Calathea care", text="…", score=0.4),
            ],
        )

        sources = client.get(f"/api/v1/diagnoses/{found}").json()["diagnosis"]["sources"]

        assert [(s["name"], s["origin"]) for s in sources] == [
            ("Botrytis (grey mould)", "knowledge_base"),
            ("rhs.org.uk", "web"),
        ]

    def test_it_carries_no_score(self, client, db, owner, seeded, corpus_retriever):
        """`M4`: corpus cosine scores and Tavily relevance scores share this list and are
        not comparable. Publishing either as a number invites comparing them."""
        found = self._diagnosis(
            db,
            owner,
            seeded,
            retrieved=[Passage(doc_id="botrytis", section="Symptoms", text="…", score=0.6)],
        )

        source = client.get(f"/api/v1/diagnoses/{found}").json()["diagnosis"]["sources"][0]

        assert "score" not in source
        assert "text" not in source

    def test_it_carries_the_tokens_and_the_cost(self, client, db, owner, seeded):
        found = self._diagnosis(
            db,
            owner,
            seeded,
            retrieved=[],
            usage={"prompt_tokens": 11482, "completion_tokens": 1464, "total_tokens": 12946},
            cost=0.0293021,
        )

        body = client.get(f"/api/v1/diagnoses/{found}").json()["diagnosis"]

        assert body["token_usage"] == {
            "prompt_tokens": 11482,
            "completion_tokens": 1464,
            "total_tokens": 12946,
        }
        assert body["cost_usd"] == 0.0293021

    def test_an_unmeasured_diagnosis_says_so_rather_than_reporting_zero(
        self, client, db, owner, seeded
    ):
        """`M18`: a failed run records no cost at all, and a diagnosis from before any of
        this was recorded has none either. Null is the honest answer; 0 would claim it was
        measured and free."""
        found = self._diagnosis(db, owner, seeded, retrieved=[])

        body = client.get(f"/api/v1/diagnoses/{found}").json()["diagnosis"]

        assert body["cost_usd"] is None
        assert body["token_usage"] is None
        assert body["sources"] == []
