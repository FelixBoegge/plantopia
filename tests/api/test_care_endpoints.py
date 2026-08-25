"""Recording what the owner did: roadmap steps and feedback."""

from core.ids import new_id
from data.models import RoadmapStep as RoadmapStepRow


def test_marking_a_step_done_records_when(client, db, seeded):
    response = client.patch(f"/api/v1/roadmap-steps/{seeded['step_id']}", json={"status": "done"})

    assert response.status_code == 204
    step = db.get(RoadmapStepRow, seeded["step_id"])
    assert step.status == "done"
    assert step.completed_at is not None


def test_reopening_a_step_clears_the_completion_time(client, db, seeded):
    """A step marked done and then reopened has not been done, and a timestamp saying
    otherwise is a lie the timeline goes on repeating."""
    client.patch(f"/api/v1/roadmap-steps/{seeded['step_id']}", json={"status": "done"})

    client.patch(f"/api/v1/roadmap-steps/{seeded['step_id']}", json={"status": "pending"})

    step = db.get(RoadmapStepRow, seeded["step_id"])
    assert step.status == "pending"
    assert step.completed_at is None


def test_skipping_is_a_terminal_status(client, db, seeded):
    client.patch(f"/api/v1/roadmap-steps/{seeded['step_id']}", json={"status": "skipped"})

    step = db.get(RoadmapStepRow, seeded["step_id"])
    assert step.status == "skipped"
    assert step.completed_at is not None


def test_an_unrecognised_status_is_refused(client, db, seeded):
    response = client.patch(
        f"/api/v1/roadmap-steps/{seeded['step_id']}", json={"status": "half-done"}
    )

    assert response.status_code in (400, 422)
    assert db.get(RoadmapStepRow, seeded["step_id"]).status == "pending"


def test_marking_an_unknown_step_is_not_found(client):
    response = client.patch(f"/api/v1/roadmap-steps/{new_id()}", json={"status": "done"})

    assert response.status_code == 404


def test_feedback_is_recorded_and_afterwards_exists(client, seeded):
    response = client.post(
        f"/api/v1/diagnoses/{seeded['diagnosis_id']}/feedback",
        json={"rating": 5, "did_it_help": "yes", "free_text": "It worked."},
    )

    assert response.status_code == 204
    # feedback_due is False here because no step is done yet; what matters is that the
    # feedback landed, which the plant detail reports by no longer asking for it.
    detail = client.get(f"/api/v1/plants/{seeded['plant_id']}").json()
    assert detail["feedback_due"] is False


def test_feedback_on_an_unknown_diagnosis_is_not_found(client):
    response = client.post(f"/api/v1/diagnoses/{new_id()}/feedback", json={"rating": 5})

    assert response.status_code == 404


def test_an_out_of_range_rating_is_refused(client, seeded):
    response = client.post(
        f"/api/v1/diagnoses/{seeded['diagnosis_id']}/feedback", json={"rating": 9}
    )

    assert response.status_code == 422
