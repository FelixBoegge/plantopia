"""Historical weather via Open-Meteo.

For outdoor plants the weather frequently *is* the diagnosis — a late frost, a
heatwave, or three weeks of rain explains symptoms that look like disease.

Open-Meteo needs no API key. Every failure returns ``None``: a missing weather input
widens the differential, it never fails the diagnosis.
"""

import logging
from datetime import UTC, date, datetime, timedelta

import httpx

from agent.schemas import WeatherDay, WeatherSummary

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

FROST_THRESHOLD_C = 0.0
HEAT_THRESHOLD_C = 32.0
_TIMEOUT = httpx.Timeout(10.0)


def get_local_weather(
    location: str,
    days_back: int = 21,
    *,
    as_of: date | None = None,
    client: httpx.Client | None = None,
) -> WeatherSummary | None:
    """Summarise recent weather at a named location.

    Args:
        location: A place name, for example "Berlin" or "Portland, Oregon".
        days_back: How many days of history to summarise.
        client: Optional httpx client, for connection reuse.

    Returns:
        A summary, or None if the location cannot be resolved or the API fails.

    Raises:
        ValueError: if ``days_back`` is not positive.
    """
    if days_back <= 0:
        raise ValueError("days_back must be positive")

    if not location.strip():
        return None

    owns_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        coordinates = _geocode(client, location)
        if coordinates is None:
            return None
        return _fetch_archive(client, *coordinates, days_back=days_back, as_of=as_of)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        logger.warning("weather lookup failed for %r", location, exc_info=True)
        return None
    finally:
        if owns_client:
            client.close()


def _geocode(client: httpx.Client, location: str) -> tuple[float, float] | None:
    response = client.get(GEOCODE_URL, params={"name": location, "count": 1})
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    return float(results[0]["latitude"]), float(results[0]["longitude"])


def _fetch_archive(
    client: httpx.Client,
    latitude: float,
    longitude: float,
    *,
    days_back: int,
    as_of: date | None = None,
) -> WeatherSummary | None:
    """The window ending the day before ``as_of``, or the day before today.

    ``as_of`` is when the photograph was taken. A plant photographed on Sunday and uploaded
    on Wednesday was not standing in Monday's and Tuesday's weather when the picture was
    made, and diagnosing it against three days it never had is a wrong answer nothing
    downstream can question — the two dates are indistinguishable once the file is stored.

    The day before, in both cases: the archive lags roughly a day, and asking for today
    returns a row of nulls that the aggregates then average.
    """
    end = (as_of or datetime.now(tz=UTC).date()) - timedelta(days=1)
    start = end - timedelta(days=days_back - 1)

    response = client.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum",
            "timezone": "UTC",
        },
    )
    response.raise_for_status()
    days = _days_from(response.json().get("daily") or {})
    return summarise(days)


def _days_from(daily: dict) -> list[WeatherDay]:
    """The service's parallel arrays, as days.

    Open-Meteo answers with one array per measure and one for the dates, all the same
    length. A day missing any of its figures is **skipped rather than zeroed**: a null
    minimum recorded as 0 °C is a frost the plant never had, which is worse than a day the
    window does not mention.
    """
    dates = daily.get("time") or []
    minima = daily.get("temperature_2m_min") or []
    maxima = daily.get("temperature_2m_max") or []
    precipitation = daily.get("precipitation_sum") or []

    days: list[WeatherDay] = []
    for index, on in enumerate(dates):
        low = _at(minima, index)
        high = _at(maxima, index)
        if low is None or high is None:
            continue
        try:
            days.append(
                WeatherDay(
                    on=date.fromisoformat(on),
                    min_temp_c=low,
                    max_temp_c=high,
                    # Precipitation is the one that may legitimately be absent while the
                    # day is otherwise usable, and zero is its honest reading.
                    precip_mm=_at(precipitation, index) or 0.0,
                )
            )
        except (TypeError, ValueError):
            continue

    return days


def _at(values: list, index: int):
    return values[index] if index < len(values) else None


def summarise(days: list[WeatherDay]) -> WeatherSummary | None:
    """The five figures callers already read, derived from the days.

    Derived rather than fetched, so a summary and its series cannot describe different
    windows. ``None`` for an empty window, which is what the caller already expects when
    nothing usable came back.
    """
    if not days:
        return None

    minima = [day.min_temp_c for day in days]
    maxima = [day.max_temp_c for day in days]

    return WeatherSummary(
        min_temp_c=min(minima),
        max_temp_c=max(maxima),
        total_precip_mm=round(sum(day.precip_mm for day in days), 2),
        frost_days=sum(1 for v in minima if v <= FROST_THRESHOLD_C),
        heat_days=sum(1 for v in maxima if v >= HEAT_THRESHOLD_C),
        days_covered=len(days),
        days=days,
    )
