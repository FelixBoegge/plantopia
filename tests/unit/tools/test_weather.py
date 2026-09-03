"""Tests for the Open-Meteo weather tool. All HTTP is mocked at the transport layer."""

import httpx
import pytest
import respx

from agent.schemas import WeatherSummary
from tools.weather import ARCHIVE_URL, GEOCODE_URL, get_local_weather

_GEOCODE_OK = {"results": [{"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}]}

_ARCHIVE_OK = {
    "daily": {
        "time": ["2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23"],
        "temperature_2m_min": [-2.0, 1.0, 3.0, 4.0],
        "temperature_2m_max": [4.0, 8.0, 36.0, 12.0],
        "precipitation_sum": [0.0, 5.5, 0.0, 2.0],
    }
}


@respx.mock
def test_returns_a_summary_for_a_known_location():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

    summary = get_local_weather("Berlin", days_back=4)

    assert isinstance(summary, WeatherSummary)
    assert summary.min_temp_c == -2.0
    assert summary.max_temp_c == 36.0
    assert summary.total_precip_mm == 7.5
    assert summary.days_covered == 4


@respx.mock
def test_counts_frost_days():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
    assert get_local_weather("Berlin", days_back=4).frost_days == 1


@respx.mock
def test_counts_heat_days():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
    assert get_local_weather("Berlin", days_back=4).heat_days == 1


@respx.mock
def test_unresolvable_location_returns_none():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    assert get_local_weather("Atlantis") is None


@respx.mock
def test_missing_results_key_returns_none():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={}))
    assert get_local_weather("Nowhere") is None


@respx.mock
def test_geocoding_server_error_returns_none():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(503))
    assert get_local_weather("Berlin") is None


@respx.mock
def test_archive_server_error_returns_none():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(500))
    assert get_local_weather("Berlin") is None


@respx.mock
def test_timeout_returns_none():
    respx.get(GEOCODE_URL).mock(side_effect=httpx.TimeoutException("slow"))
    assert get_local_weather("Berlin") is None


@respx.mock
def test_malformed_archive_payload_returns_none():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json={"daily": {}}))
    assert get_local_weather("Berlin") is None


def test_empty_location_returns_none_without_any_request():
    with respx.mock:
        assert get_local_weather("   ") is None


@respx.mock
def test_days_back_must_be_positive():
    with pytest.raises(ValueError, match="days_back"):
        get_local_weather("Berlin", days_back=0)


class TestTheWindowThisCovers:
    """Which three weeks the diagnosis is read against.

    A plant photographed on Sunday and uploaded on Wednesday was not standing in Monday's
    and Tuesday's weather when the picture was made. Anchoring on the upload diagnoses it
    against days it never had — and nothing downstream can question that, because by then
    the two dates are indistinguishable.
    """

    @respx.mock
    def test_it_spans_three_weeks_before_the_photograph_and_a_week_after(self):
        """The day of the photograph used to be dropped, which protected a photograph taken
        today at the cost of every older one. The week after it is recorded weather too,
        whenever that week has already happened, and it is the half that says whether things
        got better."""
        from datetime import date

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        get_local_weather("Berlin", 21, as_of=date(2026, 8, 10))

        params = archive.calls[0].request.url.params
        assert params["start_date"] == "2026-07-21"
        assert params["end_date"] == "2026-08-17"

    @respx.mock
    def test_the_week_after_is_clipped_where_it_has_not_happened(self):
        """A photograph from two days ago has two of its seven days on record and five still
        to come. The archive stops at yesterday; the forecast covers the rest."""
        from datetime import UTC, datetime, timedelta

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        today = datetime.now(tz=UTC).date()
        get_local_weather("Berlin", 21, as_of=today - timedelta(days=2))

        end = archive.calls[0].request.url.params["end_date"]
        assert end == (today - timedelta(days=1)).isoformat()

    @respx.mock
    def test_a_photograph_taken_today_still_stops_at_yesterday(self):
        """The archive lags about a day, and asking for today returns a row of nulls that
        the aggregates then average."""
        from datetime import UTC, datetime, timedelta

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        today = datetime.now(tz=UTC).date()
        get_local_weather("Berlin", 21, as_of=today)

        end = archive.calls[0].request.url.params["end_date"]
        assert end == (today - timedelta(days=1)).isoformat()

    @respx.mock
    def test_without_a_date_it_still_ends_yesterday(self):
        """Every caller before a photograph could say anything meant this, and still does
        when the photograph says nothing — which is most photographs."""
        from datetime import UTC, datetime, timedelta

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        get_local_weather("Berlin", 21)

        yesterday = datetime.now(tz=UTC).date() - timedelta(days=1)
        assert archive.calls[0].request.url.params["end_date"] == yesterday.isoformat()

    @respx.mock
    def test_a_three_day_delay_moves_the_whole_window(self):
        from datetime import date

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        get_local_weather("Berlin", 21, as_of=date(2026, 8, 10))
        get_local_weather("Berlin", 21, as_of=date(2026, 8, 13))

        first = archive.calls[0].request.url.params["start_date"]
        second = archive.calls[1].request.url.params["start_date"]
        assert first == "2026-07-21"
        assert second == "2026-07-24"


class TestTheDaysThemselves:
    """The window kept rather than collapsed.

    The same request already returns these; they were parsed into five numbers and the
    arrays dropped inside the function. What the five numbers cannot say is *when* — and a
    frost last night and a frost a fortnight ago are different diagnoses.
    """

    @respx.mock
    def test_every_day_comes_back_with_its_date(self):
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        summary = get_local_weather("Berlin")

        assert [day.on.isoformat() for day in summary.days] == [
            "2026-02-20",
            "2026-02-21",
            "2026-02-22",
            "2026-02-23",
        ]

    @respx.mock
    def test_a_day_carries_its_own_figures(self):
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        summary = get_local_weather("Berlin")

        first = summary.days[0]
        assert (first.min_temp_c, first.max_temp_c, first.precip_mm) == (-2.0, 4.0, 0.0)

    @respx.mock
    def test_the_summary_is_derived_from_them(self):
        """Derived rather than fetched, so a summary and its series cannot describe
        different windows."""
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        summary = get_local_weather("Berlin")

        assert summary.days_covered == len(summary.days)
        assert summary.min_temp_c == min(day.min_temp_c for day in summary.days)
        assert summary.max_temp_c == max(day.max_temp_c for day in summary.days)

    @respx.mock
    def test_a_day_the_service_had_nothing_for_is_skipped(self):
        """Not recorded as zero. A null minimum read as 0 °C is a frost the plant never
        had, which is worse than a day the window does not mention."""
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "daily": {
                        "time": ["2026-02-20", "2026-02-21", "2026-02-22"],
                        "temperature_2m_min": [5.0, None, 7.0],
                        "temperature_2m_max": [12.0, None, 14.0],
                        "precipitation_sum": [0.0, None, 1.0],
                    }
                },
            )
        )

        summary = get_local_weather("Berlin")

        assert [day.on.isoformat() for day in summary.days] == ["2026-02-20", "2026-02-22"]
        assert summary.frost_days == 0, "the missing day was not read as 0 °C"

    @respx.mock
    def test_a_day_missing_only_its_rain_is_kept(self):
        """Precipitation is the one that can legitimately be absent while the day is
        otherwise usable, and zero is its honest reading."""
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "daily": {
                        "time": ["2026-02-20"],
                        "temperature_2m_min": [5.0],
                        "temperature_2m_max": [12.0],
                        "precipitation_sum": [None],
                    }
                },
            )
        )

        summary = get_local_weather("Berlin")

        assert len(summary.days) == 1
        assert summary.days[0].precip_mm == 0.0

    @respx.mock
    def test_the_archive_is_asked_once(self):
        """Keeping the days costs nothing at the network — it is the same response."""
        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        get_local_weather("Berlin")

        assert archive.call_count == 1


class TestTheDaysAhead:
    """The forecast, built from a response recorded from the live service on 2026-08-31.

    A fixture written from documentation tests the documentation. What the recording
    established, and what these rest on: the forecast endpoint answers with exactly the
    `daily` shape the archive does — same field names, same parallel arrays — which is why
    one parser serves both and why adding this cost no new parsing code.
    """

    @staticmethod
    def recorded() -> dict:
        import json
        import pathlib

        return json.loads(
            pathlib.Path("tests/fixtures/open_meteo_forecast.json").read_text(encoding="utf-8")
        )

    @respx.mock
    def test_the_week_ahead_comes_back(self):
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=self.recorded()))

        summary = get_local_weather("Berlin")

        assert len(summary.forecast) == 7
        assert summary.forecast[0].on.isoformat() == "2026-08-31"

    @respx.mock
    def test_a_forecast_day_carries_its_figures(self):
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=self.recorded()))

        summary = get_local_weather("Berlin")

        first = summary.forecast[0]
        assert first.min_temp_c == 15.2
        assert first.max_temp_c == 21.4
        assert first.precip_mm == 9.3

    @respx.mock
    def test_it_is_anchored_on_today_not_on_the_photograph(self):
        """Two questions, two anchors. What happened to the plant is asked about the days up
        to the picture; what to do about it is asked about the days that are actually next.
        """
        from datetime import date

        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        forecast = respx.get(FORECAST_URL).mock(
            return_value=httpx.Response(200, json=self.recorded())
        )

        get_local_weather("Berlin", 21, as_of=date(2026, 8, 10))

        # The history moved with the photograph.
        assert archive.calls[0].request.url.params["start_date"] == "2026-07-21"
        # The forecast did not: it carries no date at all, only a count from now.
        assert "start_date" not in forecast.calls[0].request.url.params
        assert forecast.calls[0].request.url.params["forecast_days"] == "7"

    @respx.mock
    def test_a_failed_forecast_keeps_the_history(self):
        """The history is already in hand by then and is worth more. Losing it to a second
        request that failed would be the wrong trade."""
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(503))

        summary = get_local_weather("Berlin")

        assert summary is not None
        assert summary.days, "the history survived"
        assert summary.forecast == []

    @respx.mock
    def test_a_forecast_that_times_out_keeps_the_history(self):
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(side_effect=httpx.ReadTimeout("slow"))

        summary = get_local_weather("Berlin")

        assert summary.days
        assert summary.forecast == []

    @respx.mock
    def test_no_forecast_is_fetched_when_the_history_failed(self):
        """Nothing to attach it to, and a request for nothing is still a request."""
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(500))
        forecast = respx.get(FORECAST_URL).mock(
            return_value=httpx.Response(200, json=self.recorded())
        )

        assert get_local_weather("Berlin") is None
        assert forecast.call_count == 0


class TestBeingGivenAPosition:
    @respx.mock
    def test_no_geocoding_happens(self):
        """`M40`: a position turned into a name and resolved back into a position has made
        two round trips to arrive where it started."""
        from tools.weather import FORECAST_URL

        geocode = respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"daily": {}}))

        summary = get_local_weather("Frankfurt", position=(50.1, 8.7))

        assert summary is not None
        assert geocode.call_count == 0

    @respx.mock
    def test_the_position_is_what_is_asked_about(self):
        from tools.weather import FORECAST_URL

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"daily": {}}))

        get_local_weather("Frankfurt", position=(50.1, 8.7))

        params = archive.calls[0].request.url.params
        assert params["latitude"] == "50.1"
        assert params["longitude"] == "8.7"

    @respx.mock
    def test_a_position_works_without_a_name_at_all(self):
        """The naming service can fail while the position is perfectly good."""
        from tools.weather import FORECAST_URL

        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"daily": {}}))

        assert get_local_weather("", position=(50.1, 8.7)) is not None
