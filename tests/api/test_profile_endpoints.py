"""What has been learned about the owner, and forgetting it."""

from datetime import UTC, datetime

from data.repositories.profile import ProfileRepository

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _remember(db, owner, fact: str, confidence: float = 0.8) -> None:
    ProfileRepository(db).upsert(owner, fact=fact, source="stated", confidence=confidence, now=NOW)
    db.flush()


def test_facts_come_back_with_their_provenance(client, db, owner):
    _remember(db, owner, "lives in Berlin")

    body = client.get("/api/v1/profile/facts").json()

    assert len(body) == 1
    assert body[0]["fact"] == "lives in Berlin"
    assert body[0]["source"] == "stated"
    assert body[0]["confidence"] == 0.8
    assert body[0]["first_seen"] and body[0]["last_confirmed"]


def test_low_confidence_facts_are_shown_too(client, db, owner):
    """This is the view that says what the system believes. Hiding the weakly-held
    beliefs would make it a summary rather than a record."""
    _remember(db, owner, "tends to overwater", confidence=0.2)

    assert [f["fact"] for f in client.get("/api/v1/profile/facts").json()] == ["tends to overwater"]


def test_an_owner_with_nothing_learned_gets_an_empty_list(client):
    assert client.get("/api/v1/profile/facts").json() == []


def test_forgetting_removes_a_fact(client, db, owner):
    _remember(db, owner, "lives in Berlin")

    response = client.post("/api/v1/profile/facts/forget", json={"fact": "lives in Berlin"})

    assert response.status_code == 204
    assert client.get("/api/v1/profile/facts").json() == []


def test_forgetting_something_not_held_succeeds(client):
    """The desired state already holds, and an error would tell the owner something about
    what is stored that they did not ask."""
    response = client.post("/api/v1/profile/facts/forget", json={"fact": "never believed"})

    assert response.status_code == 204


def test_forgetting_nothing_is_refused(client):
    assert client.post("/api/v1/profile/facts/forget", json={"fact": ""}).status_code == 422
