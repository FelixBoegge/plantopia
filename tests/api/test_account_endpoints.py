"""Who am I, and what did the harness last measure.

The allowance is the part that matters most. A screen warns somebody before a run is
refused, and a warning computed differently from the refusal is a warning that will one day
be wrong in the direction nobody notices until a diagnosis fails.
"""

import json
from datetime import UTC, datetime

import pytest

from api import dependencies, errors
from core.cost import UsageSnapshot
from data.repositories.usage import UsageRepository
from identity.roles import ADMIN, MEMBER
from services import limits
from tests.people import make_user


@pytest.fixture
def spent(db, owner):
    """Record a number of runs against the signed-in owner."""

    def _spend(count: int) -> None:
        usage = UsageRepository(db)
        for _ in range(count):
            usage.record(
                owner,
                kind=limits.DIAGNOSIS,
                usage=UsageSnapshot(prompt_tokens=10, completion_tokens=5, cost_usd=0.01),
                succeeded=True,
                now=datetime.now(UTC),
            )
        db.commit()

    return _spend


def test_a_signed_in_person_can_ask_who_they_are(client, db, owner):
    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(owner)


def test_the_account_carries_the_consent_record(client, db, owner):
    """A system that infers durable facts about somebody and cannot say what they agreed to
    has no evidence of consent."""
    body = client.get("/api/v1/me").json()

    assert body["consent_version"]
    assert body["consent_at"]


def test_the_account_carries_the_tier_and_the_role(client, db, owner):
    body = client.get("/api/v1/me").json()

    assert body["tier"] == "free"
    assert body["role"] == MEMBER


def test_the_account_says_how_much_of_the_allowance_is_left(client, api_settings, spent):
    spent(3)

    body = client.get("/api/v1/me").json()

    assert body["runs_used"] == 3
    assert body["runs_allowed"] == api_settings.monthly_run_allowance
    assert body["allowance_resets_at"]


def test_the_allowance_matches_what_the_guard_would_apply(client, db, owner, api_settings, spent):
    """One computation, not two. A warning and a refusal that disagreed would be discovered
    by somebody being refused a run the screen had just said they could make.
    """
    spent(api_settings.monthly_run_allowance)
    body = client.get("/api/v1/me").json()

    assert body["runs_used"] >= body["runs_allowed"]
    with pytest.raises(limits.QuotaExceededError) as refusal:
        limits.check(
            UsageRepository(db),
            user_id=owner,
            tier="free",
            settings=api_settings,
            now=datetime.now(UTC),
        )

    assert refusal.value.limit == body["runs_allowed"]
    assert refusal.value.used == body["runs_used"]
    assert refusal.value.resets_at.isoformat() == body["allowance_resets_at"].replace("Z", "+00:00")


def test_another_owners_runs_do_not_count_against_this_one(client, db, other_owner):
    UsageRepository(db).record(
        other_owner,
        kind=limits.DIAGNOSIS,
        usage=UsageSnapshot(prompt_tokens=10, completion_tokens=5, cost_usd=0.01),
        succeeded=True,
        now=datetime.now(UTC),
    )
    db.commit()

    assert client.get("/api/v1/me").json()["runs_used"] == 0


def test_the_account_carries_no_secret(client, db, owner):
    """Not the hash, not a token, not another account's anything."""
    body = client.get("/api/v1/me").text

    assert "password" not in body
    assert "hash" not in body
    assert "token" not in body


def test_asking_who_i_am_without_a_session_is_refused(db, api_settings):
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app(api_settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.settings_dep] = lambda: api_settings

    with TestClient(app) as stranger:
        assert stranger.get("/api/v1/me").status_code == 401


def test_an_ordinary_account_cannot_read_the_evaluation_results(client, db, owner):
    response = client.get("/api/v1/evaluation/latest")

    assert response.status_code == 404
    assert response.json()["type"] == errors.TYPE_NOT_FOUND


def test_the_refusal_is_indistinguishable_from_a_route_that_does_not_exist(client, db, owner):
    """A 403 would tell a stranger the route is there."""
    refused = client.get("/api/v1/evaluation/latest")
    unknown = client.get("/api/v1/evaluation/nothing-here")

    assert refused.status_code == unknown.status_code == 404


def test_an_administrative_account_can_read_them(client, db, api_settings, tmp_path):
    from tests.api.conftest import token_for

    admin = make_user(db, role=ADMIN, verified=True)
    db.commit()
    client.headers["Authorization"] = f"Bearer {token_for(admin.id, api_settings)}"

    response = client.get("/api/v1/evaluation/latest")

    assert response.status_code == 200


def test_a_role_is_not_a_tier(client, db, api_settings):
    """Changing what somebody may spend must not change what they may reach."""
    from tests.api.conftest import token_for

    paid = make_user(db, tier="pro", role=MEMBER, verified=True)
    db.commit()
    client.headers["Authorization"] = f"Bearer {token_for(paid.id, api_settings)}"

    assert client.get("/api/v1/me").json()["tier"] == "pro"
    assert client.get("/api/v1/evaluation/latest").status_code == 404


def test_before_any_harness_has_run_the_answer_says_so(client, db, api_settings, tmp_path):
    """The ordinary state of a fresh clone. A page that failed here would send somebody
    looking for a bug instead of a command."""
    from core.config import Settings
    from tests.api.conftest import token_for
    from tests.secrets import TEST_JWT_SECRET

    empty = Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=False,
        run_sweeper_enabled=False,
        eval_results_path=tmp_path / "nothing-here",
    )
    admin = make_user(db, role=ADMIN, verified=True)
    db.commit()
    client.app.dependency_overrides[dependencies.settings_dep] = lambda: empty
    client.headers["Authorization"] = f"Bearer {token_for(admin.id, empty)}"

    response = client.get("/api/v1/evaluation/latest")

    assert response.status_code == 200
    assert response.json() == {"generated_at": None, "results": None}


def test_the_newest_result_is_the_one_returned(client, db, api_settings, tmp_path):
    from core.config import Settings
    from tests.api.conftest import token_for
    from tests.secrets import TEST_JWT_SECRET

    (tmp_path / "2026-01-01T00-00-00.json").write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00Z", "accuracy": {"top_1": 0.1}}),
        encoding="utf-8",
    )
    (tmp_path / "2026-06-01T00-00-00.json").write_text(
        json.dumps({"generated_at": "2026-06-01T00:00:00Z", "accuracy": {"top_1": 0.9}}),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=False,
        run_sweeper_enabled=False,
        eval_results_path=tmp_path,
    )
    admin = make_user(db, role=ADMIN, verified=True)
    db.commit()
    client.app.dependency_overrides[dependencies.settings_dep] = lambda: settings
    client.headers["Authorization"] = f"Bearer {token_for(admin.id, settings)}"

    body = client.get("/api/v1/evaluation/latest").json()

    assert body["generated_at"] == "2026-06-01T00:00:00Z"
    assert body["results"]["accuracy"]["top_1"] == 0.9
