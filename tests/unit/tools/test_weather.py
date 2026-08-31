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
    def test_ends_the_day_before_the_photograph_was_taken(self):
        from datetime import date

        respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json=_GEOCODE_OK))
        archive = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_ARCHIVE_OK))

        get_local_weather("Berlin", 21, as_of=date(2026, 8, 10))

        params = archive.calls[0].request.url.params
        assert params["end_date"] == "2026-08-09"
        assert params["start_date"] == "2026-07-20"

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

        first = archive.calls[0].request.url.params["end_date"]
        second = archive.calls[1].request.url.params["end_date"]
        assert first == "2026-08-09"
        assert second == "2026-08-12"


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
