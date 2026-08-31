"""The weather a diagnosis is shown.

A reading of the series rather than the series. Thirty-seven rows of unremarkable weather
bury the one frost date that explains the plant, and cost tokens on every outdoor run to do
it. So this renders three things: what was unusual and when, the week immediately before the
photograph, and the week ahead — the last because every diagnosis ends in a plan and a plan
that does not know a frost is due on Thursday has a hole in it.
"""

from collections.abc import Callable
from datetime import date

from agent.schemas import WeatherDay, WeatherSummary
from tools.weather import (
    DRY_DAY_MM,
    DRY_SPELL_DAYS,
    FROST_THRESHOLD_C,
    HEAT_THRESHOLD_C,
    WET_DAY_MM,
    WET_SPELL_DAYS,
)

# How many days of each window are shown day by day. Long enough to place the notable
# events against what came immediately before the photograph; short enough to stay a
# reading rather than a dump.
WINDOW_DAYS = 7


def render(summary: WeatherSummary) -> str:
    """The weather block, or the older one-line summary where there are no days.

    A summary without days is one built before this existed — a stored observation, or a
    fixture. It still says something true and is rendered rather than dropped.
    """
    if not summary.days:
        return _aggregate_line(summary)

    parts = [
        f"Weather where the plant is, over the {summary.days_covered} days "
        f"to {summary.days[-1].on.isoformat()}.",
        _notable(summary.days),
        _window("The last days before the photograph", summary.days[-WINDOW_DAYS:]),
    ]
    if summary.forecast:
        parts.append(_window("The days ahead, from today", summary.forecast[:WINDOW_DAYS]))

    return "\n\n".join(part for part in parts if part)


def _aggregate_line(summary: WeatherSummary) -> str:
    return (
        f"Recent weather over {summary.days_covered} days: "
        f"low {summary.min_temp_c} °C, high {summary.max_temp_c} °C, "
        f"{summary.total_precip_mm} mm rain, "
        f"{summary.frost_days} frost days, {summary.heat_days} heat days."
    )


def _notable(days: list[WeatherDay]) -> str:
    """What was unusual, with its dates. Nothing that was not.

    Everything is reported as a *run* rather than as a list of dates, which is both how a
    plant experiences it — three consecutive frosts are not the same event as three frosts a
    week apart — and what keeps this bounded when the weather is genuinely extreme.
    """
    events: list[str] = []

    for start, end, run in _runs(days, lambda d: d.min_temp_c <= FROST_THRESHOLD_C):
        low = min(d.min_temp_c for d in run)
        events.append(f"- Frost {_span(start, end)}, down to {low} °C")

    for start, end, run in _runs(days, lambda d: d.max_temp_c >= HEAT_THRESHOLD_C):
        high = max(d.max_temp_c for d in run)
        events.append(f"- Above {HEAT_THRESHOLD_C} °C {_span(start, end)}, up to {high} °C")

    for start, end, run in _runs(days, lambda d: d.precip_mm < DRY_DAY_MM, minimum=DRY_SPELL_DAYS):
        events.append(f"- No appreciable rain {_span(start, end)} ({len(run)} days)")

    for start, end, run in _runs(days, lambda d: d.precip_mm >= WET_DAY_MM, minimum=WET_SPELL_DAYS):
        total = round(sum(d.precip_mm for d in run), 1)
        events.append(f"- Persistent rain {_span(start, end)}, {total} mm over {len(run)} days")

    if not events:
        # Said in a sentence rather than demonstrated with a table. The absence of extremes
        # is itself worth knowing — it rules things out — and does not need thirty rows.
        return (
            "Nothing notable in this window: no frost, no extreme heat, no drought or "
            "prolonged wet."
        )

    return "Notable:\n" + "\n".join(events)


def _runs(
    days: list[WeatherDay],
    matches: Callable[[WeatherDay], bool],
    minimum: int = 1,
) -> list[tuple[date, date, list[WeatherDay]]]:
    """Consecutive stretches of days satisfying ``matches``, at least ``minimum`` long.

    Consecutive by *position*, not by date arithmetic: a day the service returned nothing
    usable for is absent from the series, and treating the days either side of that hole as
    adjacent would report a spell that was never observed to be unbroken.
    """
    found: list[tuple[date, date, list[WeatherDay]]] = []
    run: list[WeatherDay] = []

    for day in [*days, None]:
        if day is not None and matches(day):
            if run and (day.on - run[-1].on).days != 1:
                if len(run) >= minimum:
                    found.append((run[0].on, run[-1].on, run))
                run = []
            run.append(day)
            continue
        if len(run) >= minimum:
            found.append((run[0].on, run[-1].on, run))
        run = []

    return found


def _span(start: date, end: date) -> str:
    if start == end:
        return f"on {start.isoformat()}"
    return f"from {start.isoformat()} to {end.isoformat()}"


def _window(title: str, days: list[WeatherDay]) -> str:
    if not days:
        return ""
    rows = "\n".join(
        f"- {d.on.isoformat()}: {d.min_temp_c} to {d.max_temp_c} °C, {d.precip_mm} mm" for d in days
    )
    return f"{title}:\n{rows}"
