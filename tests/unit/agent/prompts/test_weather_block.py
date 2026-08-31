"""What the diagnosis is shown about the weather.

A reading of the series rather than the series: the dates that explain the plant, the week
before the photograph, and the week ahead. These tests assert on the rendered text, because
the rendered text is the artefact — it is what the model sees.
"""

from datetime import date, timedelta

from agent.prompts.weather import WINDOW_DAYS, render
from agent.schemas import WeatherDay, WeatherSummary
from tools.weather import summarise

START = date(2026, 8, 10)

# A 21-day window is what a diagnosis fetches, and the budget below is stated against it.
MAX_BLOCK_CHARS = 2000


def _day(index: int, *, low: float = 12.0, high: float = 22.0, rain: float = 3.0) -> WeatherDay:
    return WeatherDay(
        on=START + timedelta(days=index), min_temp_c=low, max_temp_c=high, precip_mm=rain
    )


def _window(overrides: dict[int, WeatherDay] | None = None, length: int = 21) -> WeatherSummary:
    days = [(overrides or {}).get(i) or _day(i) for i in range(length)]
    summary = summarise(days)
    assert summary is not None
    return summary


def _forecast(start: date, length: int = 7, **kwargs) -> list[WeatherDay]:
    figures = {"min_temp_c": 9.0, "max_temp_c": 20.0, "precip_mm": 0.0, **kwargs}
    return [WeatherDay(on=start + timedelta(days=i), **figures) for i in range(length)]


class TestNotableEvents:
    def test_a_frost_reaches_the_block_with_its_date(self):
        """The whole point of the change. Two frost days in three weeks cannot say whether
        they were last night or a fortnight ago, and that is the difference between frost
        damage and something else entirely."""
        block = render(_window({3: _day(3, low=-2.5)}))

        assert "2026-08-13" in block
        assert "Frost" in block
        assert "-2.5" in block

    def test_consecutive_days_are_one_event(self):
        block = render(_window({3: _day(3, low=-1.0), 4: _day(4, low=-2.0)}))

        assert "from 2026-08-13 to 2026-08-14" in block
        assert block.count("- Frost") == 1

    def test_separated_days_are_separate_events(self):
        """Three consecutive frosts are not the same event as three frosts a week apart."""
        block = render(_window({3: _day(3, low=-1.0), 10: _day(10, low=-2.0)}))

        assert block.count("- Frost") == 2

    def test_heat_is_reported(self):
        block = render(_window({5: _day(5, high=35.5)}))

        assert "2026-08-15" in block
        assert "35.5" in block

    def test_a_drought_is_reported_as_a_spell(self):
        block = render(_window({i: _day(i, rain=0.0) for i in range(2, 12)}))

        assert "No appreciable rain from 2026-08-12 to 2026-08-21" in block
        assert "10 days" in block

    def test_a_few_dry_days_are_not_a_drought(self):
        block = render(_window({i: _day(i, rain=0.0) for i in range(2, 5)}))

        assert "No appreciable rain" not in block

    def test_persistent_rain_is_reported(self):
        block = render(_window({i: _day(i, rain=20.0) for i in range(4, 8)}))

        assert "Persistent rain from 2026-08-14 to 2026-08-17" in block
        assert "80.0 mm" in block

    def test_a_gap_in_the_series_does_not_join_a_spell(self):
        """A day the service returned nothing usable for is absent from the series.
        Treating the days either side of that hole as adjacent would report a spell that was
        never observed to be unbroken."""
        # Fourteen dry days with the sixth missing: five days, a hole, then eight.
        summary = summarise([_day(i, rain=0.0) for i in range(14) if i != 5])
        assert summary is not None

        block = render(summary)

        # The eight-day stretch after the hole is a drought and is reported. The five before
        # it are not. Only pretending the missing day was dry would make one spell of
        # thirteen out of them.
        assert "No appreciable rain from 2026-08-16 to 2026-08-23 (8 days)" in block
        assert "(13 days)" not in block
        assert block.count("No appreciable rain") == 1

    def test_an_unremarkable_window_is_a_sentence_not_a_table(self):
        block = render(_window())

        assert "Nothing notable" in block
        assert "Notable:" not in block
        assert "- Frost" not in block


class TestTheTwoWindows:
    def _summary(self) -> WeatherSummary:
        summary = _window()
        summary.forecast = _forecast(date(2026, 8, 31))
        return summary

    def test_both_are_labelled_and_distinguishable(self):
        block = render(self._summary())

        assert "The last days before the photograph:" in block
        assert "The days ahead, from today:" in block
        assert block.index("before the photograph") < block.index("days ahead")

    def test_the_history_window_is_the_days_immediately_before(self):
        history = render(self._summary()).split("The days ahead")[0]

        assert "2026-08-30" in history  # the last day fetched
        assert "2026-08-24" in history  # seven days back
        assert "2026-08-23" not in history  # and no further

    def test_each_day_carries_its_figures(self):
        assert "2026-08-30: 12.0 to 22.0 °C, 3.0 mm" in render(self._summary())

    def test_a_missing_forecast_leaves_the_history_intact(self):
        """The forecast is a second request and can fail on its own. A history without one
        is a worse plan, not a failed diagnosis."""
        block = render(_window())

        assert "The last days before the photograph:" in block
        assert "days ahead" not in block

    def test_neither_window_exceeds_its_length(self):
        summary = self._summary()
        summary.forecast = _forecast(date(2026, 8, 31), length=14)

        rows = [line for line in render(summary).splitlines() if line.startswith("- 2026-")]

        assert len(rows) == WINDOW_DAYS * 2


class TestTheBlockIsBounded:
    def test_an_ordinary_window_is_small(self):
        assert len(render(_window())) < 500

    def test_the_worst_case_stays_within_the_budget(self):
        """Maximum fragmentation: alternate days are simultaneously a frost, a heat day and
        dry, so every qualifying day becomes its own run rather than joining a neighbour.
        Meteorologically absurd, which is the point — it is the upper bound on the shape."""
        summary = _window(
            {i: _day(i, low=-10.0, high=40.0, rain=0.0) for i in range(21) if i % 2 == 0}
        )
        summary.forecast = _forecast(
            date(2026, 9, 1), min_temp_c=-10.0, max_temp_c=40.0, precip_mm=100.0
        )

        assert len(render(summary)) < MAX_BLOCK_CHARS


class TestASummaryWithoutDays:
    def test_the_older_line_is_still_rendered(self):
        """An observation recorded before this existed. It still says something true, and
        dropping it would silently remove weather from a case that had it."""
        block = render(
            WeatherSummary(
                min_temp_c=2.0,
                max_temp_c=28.0,
                total_precip_mm=41.0,
                frost_days=0,
                heat_days=0,
                days_covered=21,
            )
        )

        assert "Recent weather over 21 days" in block
        assert "41.0 mm rain" in block


class TestItReachesTheCase:
    def test_the_frost_date_survives_into_the_prompt(self, sample_images):
        """Rendering it correctly and never calling it would be the same as not having it."""
        from tests.unit.agent.nodes.test_diagnose import _case, _state

        state = _state(sample_images)
        state.weather = _window({3: _day(3, low=-2.5)})

        assert "2026-08-13" in _case(state)
