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


def _diagnosed(db, owner, *, cost_usd, token_usage) -> None:
    """A plant with one diagnosis carrying the given spend, on this owner."""
    from agent.schemas import Candidate, Differential, Severity
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository

    now = datetime.now(UTC)
    plant_id = PlantRepository(db).create(
        owner,
        name="Test plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now,
    )
    observation_id = ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=["img-1"], user_notes=None, now=now
    )
    DiagnosisRepository(db).create(
        owner,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=Differential(
            is_healthy=False,
            reasoning="Test reasoning.",
            candidates=[
                Candidate(
                    disorder_id="overwatering",
                    name="Overwatering",
                    probability=0.8,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=[],
                    distinguishing_test="Feel the soil three days after watering.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                ),
                Candidate(
                    disorder_id="root-rot",
                    name="Root rot",
                    probability=0.2,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=["stem firm"],
                    distinguishing_test="Unpot the plant and inspect the roots.",
                    severity=Severity.ACT_TODAY,
                    transmissible=False,
                ),
            ],
        ),
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now,
        cost_usd=cost_usd,
        token_usage=token_usage,
    )
    db.commit()


def test_the_account_carries_the_total_spend_across_every_plant(client, db, owner):
    _diagnosed(
        db,
        owner,
        cost_usd=0.0042,
        token_usage={"prompt_tokens": 900, "completion_tokens": 344, "total_tokens": 1244},
    )
    _diagnosed(
        db,
        owner,
        cost_usd=0.0058,
        token_usage={"prompt_tokens": 1100, "completion_tokens": 400, "total_tokens": 1500},
    )

    body = client.get("/api/v1/me").json()["total_spend"]

    assert body["diagnosis_count"] == 2
    assert body["cost_usd"] == pytest.approx(0.01)
    assert body["token_usage"] == {
        "prompt_tokens": 2000,
        "completion_tokens": 744,
        "total_tokens": 2744,
    }


def test_another_owners_diagnoses_do_not_count_toward_this_ones_total(
    client, db, owner, other_owner
):
    _diagnosed(
        db,
        other_owner,
        cost_usd=9.99,
        token_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    )

    body = client.get("/api/v1/me").json()["total_spend"]

    assert body["diagnosis_count"] == 0
    assert body["cost_usd"] is None


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
    """Not the hash, not an access or refresh token, not another account's anything.

    Checked by name rather than by the bare word "token": `total_spend.token_usage` is a
    legitimate, non-secret field — what an LLM call cost, not an authentication token —
    and would false-positive a blanket substring check.
    """
    body = client.get("/api/v1/me").text

    assert "password" not in body
    assert "hash" not in body
    assert "access_token" not in body
    assert "refresh_token" not in body


def test_asking_who_i_am_without_a_session_is_refused(db, api_settings):
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app(api_settings)
    app.dependency_overrides[dependencies.session_dep] = lambda: db
    app.dependency_overrides[dependencies.settings_dep] = lambda: api_settings

    with TestClient(app) as stranger:
        assert stranger.get("/api/v1/me").status_code == 401


class TestWhatTheAccountMayReach:
    """`/me` says whether this account may read the evaluation results.

    The client used to decide that for itself, from `account.role === "admin"` in
    `AppHeader` — a second copy of an authorization rule, in the place least able to keep
    up with it. It was already wrong once `PLANTOPIA_EVALUATION_OPEN_TO_MEMBERS` existed:
    the deployment had opened the page and the navigation went on hiding the link.

    So the server answers it, with the same function the endpoint guards itself by. A
    client showing a link it cannot follow and a client hiding one it can are the same
    bug, and neither is the client's to get right.
    """

    def test_an_administrator_may(self, client, db, api_settings):
        from tests.api.conftest import token_for

        admin = make_user(db, role=ADMIN, verified=True)
        db.commit()
        client.headers["Authorization"] = f"Bearer {token_for(admin.id, api_settings)}"

        assert client.get("/api/v1/me").json()["may_read_evaluations"] is True

    def test_an_ordinary_member_may_not(self, client, db, owner):
        assert client.get("/api/v1/me").json()["may_read_evaluations"] is False

    def test_a_member_may_when_the_deployment_opens_it(self, client, db):
        from core.config import Settings
        from tests.api.conftest import token_for
        from tests.secrets import TEST_JWT_SECRET

        opened = Settings(
            _env_file=None,
            openrouter_api_key="sk-test",
            jwt_secret=TEST_JWT_SECRET,
            secure_cookies=False,
            run_sweeper_enabled=False,
            evaluation_open_to_members=True,
        )
        member = make_user(db, role=MEMBER, verified=True)
        db.commit()
        client.app.dependency_overrides[dependencies.settings_dep] = lambda: opened
        client.headers["Authorization"] = f"Bearer {token_for(member.id, opened)}"

        assert client.get("/api/v1/me").json()["may_read_evaluations"] is True

    def test_it_agrees_with_what_the_endpoint_actually_allows(self, client, db, owner):
        """The point of moving it to the server: one answer, not two that can drift."""
        claimed = client.get("/api/v1/me").json()["may_read_evaluations"]
        allowed = client.get("/api/v1/evaluation/latest").status_code == 200

        assert claimed == allowed


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


def test_a_deployment_may_open_the_results_to_members(client, db, api_settings):
    """Temporary, for the capstone review: the reviewer registers an ordinary account and
    still has to reach the numbers.

    Carried by configuration rather than by the rule in `identity/roles.py`, so that the
    deployed default stays admin-only and re-locking is deleting a line from `.env`. The
    three tests above pin that default and pass unchanged — which is the point of choosing
    a switch over an edit.
    """
    from core.config import Settings
    from tests.api.conftest import token_for
    from tests.secrets import TEST_JWT_SECRET

    opened = Settings(
        _env_file=None,
        openrouter_api_key="sk-test",
        jwt_secret=TEST_JWT_SECRET,
        secure_cookies=False,
        run_sweeper_enabled=False,
        evaluation_open_to_members=True,
    )
    member = make_user(db, role=MEMBER, verified=True)
    db.commit()
    client.app.dependency_overrides[dependencies.settings_dep] = lambda: opened
    client.headers["Authorization"] = f"Bearer {token_for(member.id, opened)}"

    assert client.get("/api/v1/evaluation/latest").status_code == 200


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
