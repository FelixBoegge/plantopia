"""Fetching one diagnosis.

The run reports an identifier when it completes. If that identifier cannot be resolved, the
client has been handed a receipt rather than a result.
"""

from core.ids import new_id


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
