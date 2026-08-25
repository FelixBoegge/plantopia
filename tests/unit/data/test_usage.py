"""Recording what runs cost.

The distinction that matters here is unknown versus zero. A provider that reports tokens
but no price must not leave behind a row that reads as a free run, because a free run is
exactly what somebody trying to spend the budget would like their runs to look like.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.cost import UsageSnapshot
from data.models import UsageEvent
from data.repositories.usage import UsageRepository

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
MEASURED = UsageSnapshot(prompt_tokens=1200, completion_tokens=300, cost_usd=0.047)
UNPRICED = UsageSnapshot(prompt_tokens=1200, completion_tokens=300, cost_usd=None)


@pytest.fixture
def usage(db):
    return UsageRepository(db)


def test_a_successful_run_records_its_tokens_and_cost(usage, db, owner):
    event_id = usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)

    stored = db.get(UsageEvent, event_id)
    assert (stored.prompt_tokens, stored.completion_tokens) == (1200, 300)
    assert stored.cost_usd == pytest.approx(0.047)
    assert stored.succeeded is True


def test_a_failed_run_is_recorded_all_the_same(usage, db, owner):
    """Attributing spend to the diagnosis it produced would record nothing for a run that
    made expensive calls and then failed.
    """
    event_id = usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=False, now=NOW)

    stored = db.get(UsageEvent, event_id)
    assert stored.succeeded is False
    assert stored.cost_usd == pytest.approx(0.047)


def test_an_unpriced_run_records_its_tokens(usage, db, owner):
    event_id = usage.record(owner, kind="diagnosis", usage=UNPRICED, succeeded=True, now=NOW)

    assert db.get(UsageEvent, event_id).prompt_tokens == 1200


def test_unknown_cost_is_distinguishable_from_zero(usage, db, owner):
    """Null, not 0.0. An unmeasured run must not be readable as a free one."""
    unknown = usage.record(owner, kind="diagnosis", usage=UNPRICED, succeeded=True, now=NOW)
    free = usage.record(
        owner,
        kind="diagnosis",
        usage=UsageSnapshot(prompt_tokens=0, completion_tokens=0, cost_usd=0.0),
        succeeded=True,
        now=NOW,
    )

    assert db.get(UsageEvent, unknown).cost_usd is None
    assert db.get(UsageEvent, free).cost_usd == 0.0


def test_a_run_with_no_usage_at_all_is_still_a_run(usage, db, owner):
    event_id = usage.record(owner, kind="diagnosis", usage=None, succeeded=False, now=NOW)

    stored = db.get(UsageEvent, event_id)
    assert stored.prompt_tokens == 0
    assert stored.cost_usd is None


def test_counting_runs_sees_only_this_owners(usage, db, owner, other_owner):
    usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)
    for _ in range(3):
        usage.record(other_owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)

    assert usage.count_runs(owner, kind="diagnosis", since=NOW - timedelta(days=1)) == 1


def test_counting_runs_sees_only_the_kind_asked_for(usage, db, owner):
    usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)
    usage.record(owner, kind="recheck", usage=MEASURED, succeeded=True, now=NOW)

    assert usage.count_runs(owner, kind="diagnosis", since=NOW - timedelta(days=1)) == 1


def test_counting_runs_ignores_anything_before_the_moment(usage, db, owner):
    usage.record(
        owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW - timedelta(days=2)
    )
    usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)

    assert usage.count_runs(owner, kind="diagnosis", since=NOW - timedelta(days=1)) == 1


def test_total_spend_crosses_owners(usage, db, owner, other_owner):
    """The one method here that is allowed to: the cap is a property of the deployment."""
    usage.record(owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)
    usage.record(other_owner, kind="diagnosis", usage=MEASURED, succeeded=True, now=NOW)

    assert usage.total_spend_since(NOW - timedelta(days=1)) == pytest.approx(0.094)


def test_total_spend_is_zero_when_nothing_was_recorded(usage, db):
    """A sum over no rows is 0.0, not null — the caller compares it against a cap."""
    assert usage.total_spend_since(NOW) == 0.0


def test_unpriced_runs_contribute_nothing_to_the_total(usage, db, owner):
    """Understating rather than guessing. A cap that invented a price would refuse people
    on the strength of a number nobody measured.
    """
    for _ in range(10):
        usage.record(owner, kind="diagnosis", usage=UNPRICED, succeeded=True, now=NOW)

    assert usage.total_spend_since(NOW - timedelta(days=1)) == 0.0
