"""The two ceilings on model spend.

Boundaries are asserted on both sides — at the limit and one below it — because an
off-by-one here either lets one extra run through or refuses somebody who has room.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.config import Settings
from core.cost import UsageSnapshot
from data.repositories.usage import UsageRepository
from services import limits
from services.limits import DailyCapReachedError, QuotaExceededError
from tests.secrets import TEST_JWT_SECRET

MARCH = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
COST = UsageSnapshot(prompt_tokens=1000, completion_tokens=200, cost_usd=0.05)


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, **overrides
    )


@pytest.fixture
def usage(db):
    return UsageRepository(db)


def _run(usage, owner, *, when=MARCH, cost=COST, succeeded=True):
    return usage.record(owner, kind=limits.DIAGNOSIS, usage=cost, succeeded=succeeded, now=when)


def _check(usage, owner, settings, *, tier="free", now=MARCH):
    limits.check(usage, user_id=owner, tier=tier, settings=settings, now=now)


def test_a_run_below_the_allowance_proceeds(usage, db, owner):
    settings = _settings(monthly_run_allowance=3)
    _run(usage, owner)

    _check(usage, owner, settings)  # must not raise


def test_a_run_at_the_allowance_is_refused(usage, db, owner):
    settings = _settings(monthly_run_allowance=3)
    for _ in range(3):
        _run(usage, owner)

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings)


def test_the_last_permitted_run_still_proceeds(usage, db, owner):
    """The other side of the boundary, so the comparison cannot drift by one."""
    settings = _settings(monthly_run_allowance=3)
    for _ in range(2):
        _run(usage, owner)

    _check(usage, owner, settings)


def test_the_refusal_says_what_the_limit_is_and_when_it_resets(usage, db, owner):
    """An interface has to render this, and a sentence is not something it can render."""
    settings = _settings(monthly_run_allowance=2)
    for _ in range(2):
        _run(usage, owner)

    with pytest.raises(QuotaExceededError) as refusal:
        _check(usage, owner, settings)

    assert refusal.value.limit == 2
    assert refusal.value.used == 2
    assert refusal.value.resets_at == datetime(2026, 4, 1, tzinfo=UTC)


def test_failed_runs_count_against_the_allowance(usage, db, owner):
    """A quota that cannot see them is one somebody can exhaust the budget through."""
    settings = _settings(monthly_run_allowance=2)
    _run(usage, owner, succeeded=False)
    _run(usage, owner, succeeded=False)

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings)


def test_a_run_with_no_measured_cost_still_counts(usage, db, owner):
    """Otherwise the way to run for free is to make the provider not report."""
    settings = _settings(monthly_run_allowance=1)
    _run(usage, owner, cost=None)

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings)


def test_last_months_runs_do_not_count(usage, db, owner):
    settings = _settings(monthly_run_allowance=2)
    for _ in range(5):
        _run(usage, owner, when=datetime(2026, 2, 28, 23, 59, tzinfo=UTC))

    _check(usage, owner, settings)


def test_the_period_rolls_over_at_the_month(usage, db, owner):
    settings = _settings(monthly_run_allowance=2)
    for _ in range(2):
        _run(usage, owner, when=datetime(2026, 3, 31, 23, 0, tzinfo=UTC))

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings, now=datetime(2026, 3, 31, 23, 30, tzinfo=UTC))
    _check(usage, owner, settings, now=datetime(2026, 4, 1, 0, 30, tzinfo=UTC))


def test_a_period_ending_in_december_rolls_into_january(usage, db, owner):
    """The one arithmetic in this module that has an edge, so it has a test."""
    assert limits.period_end(datetime(2026, 12, 9, tzinfo=UTC)) == datetime(2027, 1, 1, tzinfo=UTC)


def test_another_tier_applies_without_a_code_change(usage, db, owner):
    settings = _settings(monthly_run_allowance=2, tier_allowances={"pro": 100})
    for _ in range(5):
        _run(usage, owner)

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings, tier="free")
    _check(usage, owner, settings, tier="pro")


def test_an_unrecognised_tier_gets_the_default_allowance(usage, db, owner):
    """Not zero and not unlimited: a tier nobody configured should be an ordinary account."""
    settings = _settings(monthly_run_allowance=2, tier_allowances={"pro": 100})
    for _ in range(2):
        _run(usage, owner)

    with pytest.raises(QuotaExceededError):
        _check(usage, owner, settings, tier="something-nobody-configured")


def test_one_owners_runs_do_not_count_against_another(usage, db, owner, other_owner):
    settings = _settings(monthly_run_allowance=2)
    for _ in range(5):
        _run(usage, other_owner)

    _check(usage, owner, settings)


def test_below_the_daily_cap_a_run_proceeds(usage, db, owner):
    settings = _settings(daily_spend_cap_usd=1.0)
    _run(usage, owner)

    _check(usage, owner, settings)


def test_at_the_daily_cap_every_run_is_refused(usage, db, owner, other_owner):
    """Including for an owner with allowance to spare — that is the point of it."""
    settings = _settings(daily_spend_cap_usd=0.10, monthly_run_allowance=1000)
    _run(usage, other_owner)
    _run(usage, other_owner)

    with pytest.raises(DailyCapReachedError):
        _check(usage, owner, settings)


def test_the_daily_cap_counts_everybody_together(usage, db, owner, other_owner):
    settings = _settings(daily_spend_cap_usd=0.10, monthly_run_allowance=1000)
    _run(usage, owner)
    _run(usage, other_owner)

    with pytest.raises(DailyCapReachedError):
        _check(usage, owner, settings)


def test_yesterdays_spend_does_not_count(usage, db, owner):
    settings = _settings(daily_spend_cap_usd=0.10, monthly_run_allowance=1000)
    for _ in range(10):
        _run(usage, owner, when=MARCH - timedelta(days=1))

    _check(usage, owner, settings)


def test_a_new_day_clears_the_cap(usage, db, owner):
    settings = _settings(daily_spend_cap_usd=0.10, monthly_run_allowance=1000)
    for _ in range(5):
        _run(usage, owner, when=datetime(2026, 3, 15, 23, 0, tzinfo=UTC))

    with pytest.raises(DailyCapReachedError):
        _check(usage, owner, settings, now=datetime(2026, 3, 15, 23, 30, tzinfo=UTC))
    _check(usage, owner, settings, now=datetime(2026, 3, 16, 0, 30, tzinfo=UTC))


def test_the_cap_says_when_it_resets(usage, db, owner):
    settings = _settings(daily_spend_cap_usd=0.01)
    _run(usage, owner)

    with pytest.raises(DailyCapReachedError) as refusal:
        _check(usage, owner, settings)

    assert refusal.value.resets_at == datetime(2026, 3, 16, tzinfo=UTC)


def test_the_two_refusals_are_different_exceptions(usage, db, owner):
    """A client has to tell them apart: one is waitable, the other is not."""
    assert not issubclass(QuotaExceededError, DailyCapReachedError)
    assert not issubclass(DailyCapReachedError, QuotaExceededError)


def test_the_cap_is_checked_before_the_personal_quota(usage, db, owner):
    """When both are reached, the one the person can do nothing about is the useful one."""
    settings = _settings(daily_spend_cap_usd=0.01, monthly_run_allowance=1)
    _run(usage, owner)

    with pytest.raises(DailyCapReachedError):
        _check(usage, owner, settings)


def test_an_unmeasured_run_does_not_inflate_the_cap(usage, db, owner):
    """A cap that guessed at unreported cost would refuse people on a number nobody
    measured. Understating is the safer direction.
    """
    settings = _settings(daily_spend_cap_usd=0.01, monthly_run_allowance=1000)
    for _ in range(100):
        _run(usage, owner, cost=UsageSnapshot(prompt_tokens=10, completion_tokens=5, cost_usd=None))

    _check(usage, owner, settings)
