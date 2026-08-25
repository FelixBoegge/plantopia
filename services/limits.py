"""What stops the model bill from being unbounded.

Two ceilings, and they answer different questions.

**The personal quota** bounds what one account can run in a month. It exists so that one
person cannot spend the budget, and it is the one a person can do something about — wait for
the period, or move to a tier with more room.

**The daily cap** bounds what everybody together can spend in a day. Per-person quotas do
not bound what a thousand fresh accounts can do, and with open registration a thousand fresh
accounts is a morning's work. Nothing a person does clears this one, which is why its
refusal has to be distinguishable from the other.

Both refuse *before* any model call. A guard that runs afterwards has already spent the
money it was there to protect.

``services/run_service.start`` calls ``check`` before a run row exists, and
``runs/worker`` calls ``UsageRepository.record`` on the way out of every terminal status.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from core.config import Settings
from data.repositories.usage import UsageRepository

# The kind recorded for a diagnosis run. A string rather than an enum because the set grows
# from the outside — a recheck, a chat turn — and a table of kinds nobody reads is a table.
DIAGNOSIS = "diagnosis"


class LimitReachedError(Exception):
    """A run was refused by a ceiling. Subclasses say which."""


@dataclass(frozen=True, slots=True)
class QuotaExceededError(LimitReachedError):
    """This account has used its allowance for the period.

    Carries the numbers rather than a sentence, so an interface can say "18 of 20 used,
    resets on the 1st" instead of repeating whatever prose happened to be written here.
    """

    limit: int
    used: int
    resets_at: datetime

    def __str__(self) -> str:
        return f"{self.used} of {self.limit} runs used; resets at {self.resets_at.isoformat()}"


@dataclass(frozen=True, slots=True)
class DailyCapReachedError(LimitReachedError):
    """Everybody together has reached the day's spend.

    Distinct from the quota because the person can do nothing about it, and telling them to
    wait for their monthly period would be advice that does not apply.
    """

    cap_usd: float
    spent_usd: float
    resets_at: datetime

    def __str__(self) -> str:
        return f"the daily cap of ${self.cap_usd:.2f} has been reached"


def allowance_for(tier: str, settings: Settings) -> int:
    """How many runs a tier permits in a period.

    Read from settings rather than a table in code, so introducing a second tier is a
    configuration change. A tier nobody has configured falls back to the default allowance
    rather than to zero or to infinity: an unrecognised tier should be an ordinary account,
    not a locked one and not a free-for-all.
    """
    return settings.tier_allowances.get(tier, settings.monthly_run_allowance)


def period_start(now: datetime) -> datetime:
    """The beginning of the current period.

    The calendar month, in UTC. Not a rolling thirty days: a person watching their usage
    should be able to say when it resets without knowing when they last ran anything.
    """
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


def period_end(now: datetime) -> datetime:
    """When the current period rolls over."""
    if now.month == 12:
        return period_start(now).replace(year=now.year + 1, month=1)
    return period_start(now).replace(month=now.month + 1)


def day_start(now: datetime) -> datetime:
    """Midnight UTC. One timezone, so the cap does not reset twice or not at all."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


def day_end(now: datetime) -> datetime:
    """The next midnight UTC."""
    from datetime import timedelta

    return day_start(now) + timedelta(days=1)


def check(
    usage: UsageRepository,
    *,
    user_id: UUID,
    tier: str,
    kind: str = DIAGNOSIS,
    settings: Settings,
    now: datetime,
) -> None:
    """Refuse a run that either ceiling forbids. Returns nothing when it may proceed.

    The daily cap is checked first. When both are reached, the one the person can do
    nothing about is the more useful thing to be told.
    """
    spent = usage.total_spend_since(day_start(now))
    if spent >= settings.daily_spend_cap_usd:
        raise DailyCapReachedError(
            cap_usd=settings.daily_spend_cap_usd, spent_usd=spent, resets_at=day_end(now)
        )

    limit = allowance_for(tier, settings)
    used = usage.count_runs(user_id, kind=kind, since=period_start(now))
    if used >= limit:
        raise QuotaExceededError(limit=limit, used=used, resets_at=period_end(now))
