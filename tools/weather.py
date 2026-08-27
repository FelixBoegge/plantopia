"""Historical weather via Open-Meteo.

For outdoor plants the weather frequently *is* the diagnosis — a late frost, a
heatwave, or three weeks of rain explains symptoms that look like disease.

Open-Meteo needs no API key. Every failure returns ``None``: a missing weather input
widens the differential, it never fails the diagnosis.
"""

import logging
from datetime import UTC, date, datetime, timedelta

import httpx

from agent.schemas import WeatherSummary

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
    daily = response.json().get("daily") or {}

    minima = daily.get("temperature_2m_min") or []
    maxima = daily.get("temperature_2m_max") or []
    precipitation = daily.get("precipitation_sum") or []

    if not minima or not maxima:
        return None

    minima = [v for v in minima if v is not None]
    maxima = [v for v in maxima if v is not None]
    precipitation = [v for v in precipitation if v is not None]

    if not minima or not maxima:
        return None

    return WeatherSummary(
        min_temp_c=min(minima),
        max_temp_c=max(maxima),
        total_precip_mm=round(sum(precipitation), 2),
        frost_days=sum(1 for v in minima if v <= FROST_THRESHOLD_C),
        heat_days=sum(1 for v in maxima if v >= HEAT_THRESHOLD_C),
        days_covered=len(minima),
    )
