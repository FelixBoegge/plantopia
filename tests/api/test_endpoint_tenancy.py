"""Every route that names a resource, asked as somebody else.

The mirror of `tests/unit/data/test_tenancy.py`, one layer up. The repositories already
refuse another owner; this asserts the HTTP layer does not undo that refusal — by leaking
the record, or by saying *403*, which tells a stranger the thing exists while appearing to
protect it.

**The status code is asserted, not just the absence of data.** A handler that caught the
repository's refusal and re-raised it as "forbidden" would satisfy a body-only check.

**Two real accounts.** Each request carries a bearer token for the second one, and the
owner is resolved from that token the same way a browser's would be. Nothing about who is
asking is overridden, which is what closes `M27`.
"""

from datetime import UTC, datetime

import pytest

from api import dependencies
from tests.api.conftest import token_for

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

# (label, method, path template, body) for every route taking a resource identifier.
# Bodies are per route rather than per method: a PATCH to a plant and a PATCH to a
# roadmap step want different shapes, and sending the wrong one would fail validation
# before the handler ever decided whose record it was — which would pass this test for
# entirely the wrong reason.
ROUTES = [
    ("plants.get", "GET", "/api/v1/plants/{plant_id}", None),
    ("plants.rename", "PATCH", "/api/v1/plants/{plant_id}", {"name": "stolen"}),
    ("plants.delete", "DELETE", "/api/v1/plants/{plant_id}", None),
    ("chat.list", "GET", "/api/v1/plants/{plant_id}/messages", None),
    ("chat.send", "POST", "/api/v1/plants/{plant_id}/messages", {"content": "hello"}),
    (
        "chat.stream",
        "POST",
        "/api/v1/plants/{plant_id}/messages/stream",
        {"content": "hello"},
    ),
    ("care.mark_step", "PATCH", "/api/v1/roadmap-steps/{step_id}", {"status": "done"}),
    ("care.feedback", "POST", "/api/v1/diagnoses/{diagnosis_id}/feedback", {"rating": 5}),
    ("photos.get", "GET", "/api/v1/photos/{key}", None),
    ("runs.get", "GET", "/api/v1/runs/{run_id}", None),
    ("runs.answer", "POST", "/api/v1/runs/{run_id}/answers", {"answers": {"watering": "daily"}}),
    ("runs.cancel", "DELETE", "/api/v1/runs/{run_id}", None),
    ("runs.events", "GET", "/api/v1/runs/{run_id}/events", None),
]


@pytest.fixture
def as_other_owner(client, db, other_owner, api_settings, make_deps):
    """The same application, asked by a second registered account.

    The token is real and the owner is resolved from it. The chat service is still
    substituted, and not for convenience: the real dependency builds model clients and a
    Chroma collection, which would embed the corpus over the network. Every request here is
    refused long before it reaches a model, but a dependency is built before a handler runs.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from data.repositories.messages import MessageRepository
    from services.chat_service import ChatService

    client.app.dependency_overrides[dependencies.chat_service] = lambda: ChatService(
        deps=make_deps(user_id=other_owner),
        messages=MessageRepository(db),
        checkpointer=MemorySaver(),
        now=lambda: NOW,
    )
    client.headers["Authorization"] = f"Bearer {token_for(other_owner, api_settings)}"
    return client


@pytest.mark.parametrize("label,method,template,body", ROUTES, ids=[r[0] for r in ROUTES])
def test_another_owner_gets_not_found(as_other_owner, seeded, label, method, template, body):
    path = template.format(key=seeded["photo_key"], **seeded)

    response = as_other_owner.request(method, path, json=body)

    assert response.status_code == 404, f"{label} answered {response.status_code}"
    assert response.status_code != 403, (
        f"{label} said forbidden, which tells a stranger the resource exists"
    )


@pytest.mark.parametrize("label,method,template,body", ROUTES, ids=[r[0] for r in ROUTES])
def test_the_refusal_looks_like_an_unknown_resource(
    as_other_owner, seeded, label, method, template, body
):
    """Absent and forbidden must be one answer, body included."""
    from core.ids import new_id

    theirs = template.format(key=seeded["photo_key"], **seeded)
    absent = dict.fromkeys([*seeded, "key"], new_id())
    nothing = template.format(**absent)

    refused = as_other_owner.request(method, theirs, json=body)
    unknown = as_other_owner.request(method, nothing, json=body)

    assert refused.status_code == unknown.status_code
    assert refused.json() == unknown.json()


def test_another_owner_sees_none_of_the_plants(as_other_owner, seeded):
    assert as_other_owner.get("/api/v1/plants").json() == []


def test_another_owner_sees_none_of_the_facts(as_other_owner, db, owner):
    from datetime import UTC, datetime

    from data.repositories.profile import ProfileRepository

    ProfileRepository(db).upsert(
        owner,
        fact="lives in Berlin",
        source="stated",
        confidence=0.8,
        now=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    db.flush()

    assert as_other_owner.get("/api/v1/profile/facts").json() == []


def test_a_refused_write_changes_nothing(as_other_owner, db, seeded):
    """A 404 that had already written would be worse than a 200."""
    from data.models import Plant

    as_other_owner.patch(f"/api/v1/plants/{seeded['plant_id']}", json={"name": "stolen"})
    db.expire_all()

    assert db.get(Plant, seeded["plant_id"]).name == "Kitchen basil"


def test_a_refused_delete_leaves_the_plant(as_other_owner, db, seeded):
    from data.models import Plant

    as_other_owner.delete(f"/api/v1/plants/{seeded['plant_id']}")
    db.expire_all()

    assert db.get(Plant, seeded["plant_id"]) is not None


def test_the_route_table_covers_every_route_taking_an_identifier(client):
    """The test for the test: a route added later with a path parameter and left out of
    ROUTES would otherwise go unchecked, which is exactly how a hole gets in."""
    schema = client.app.openapi()
    with_parameters = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if "{" in path
    }
    covered = {(method, template) for _, method, template, _ in ROUTES}

    assert with_parameters == covered, (
        f"routes taking an identifier but absent from ROUTES: {sorted(with_parameters - covered)}"
    )
