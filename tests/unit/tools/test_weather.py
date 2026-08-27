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
