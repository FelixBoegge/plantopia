"""Turning a coarse position into a place somebody recognises.

A pair of decimal numbers is not something a person can confirm or correct. "Near Berlin" is.
That is the whole job: the position is what the weather lookup uses, and the name is what
makes it checkable by the only person who knows whether it is right.

**Keyless, on purpose.** Nominatim is OpenStreetMap's own service and needs no credential, so
this path works on a fresh clone rather than being dark until somebody registers — which is
what `U1` records about the web-search path, and what this change is in a position to avoid.

Its terms are the cost, and they are requirements rather than courtesies:

- A `User-Agent` that identifies the application. The default below does; a deployment should
  set its own with a real contact address.
- At most one request a second. The cache is what keeps ordinary use well inside that — every
  photograph from one garden rounds to the same coarse position, so a person diagnosing the
  same plant weekly makes one lookup rather than one a week.
- Attribution for the data wherever it is shown, which the interface does.

**Every failure returns nothing.** This is the first external call in this project that
happens while somebody is waiting to press a button rather than inside a ninety-second run,
so it gets a short timeout and no ability to fail anything: without a name, the coordinates
are shown instead.
"""

import logging
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://nominatim.openstreetmap.org/reverse"

# Identifies the application, as the terms require. A deployment should replace it with one
# carrying a real contact address — `PLANTOPIA_GEOCODING_USER_AGENT`.
DEFAULT_USER_AGENT = "Plantopia/1.0 (plant health assistant; https://github.com/plantopia)"

# Short, because somebody is watching an upload finish. Long enough for a service that is
# free and occasionally slow.
_TIMEOUT = httpx.Timeout(5.0)

# Roughly city level. Asking for more detail than the position carries would invite a street
# name for a position that is accurate to eleven kilometres, which would be a lie with a
# very convincing format.
_ZOOM = 10

# The address fields that name somewhere a person would recognise, most specific first. A
# reverse lookup at this zoom answers with whichever of these the place has.
_PLACE_FIELDS = (
    "city",
    "town",
    "village",
    "municipality",
    "suburb",
    "county",
    "state",
    "country",
)


def place_name(
    latitude: float,
    longitude: float,
    *,
    base_url: str = DEFAULT_URL,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str | None:
    """Name the place at a coarse position, or return ``None``.

    Args:
        latitude, longitude: A position already coarsened by `core.metadata`. This function
            does no rounding of its own — it is not the place that decides how precise a
            stored position is, and doing it in two places would mean two things to keep in
            step.

    Returns:
        A name, or ``None`` when the service is unavailable, answers with nothing usable, or
        answers with something that will not parse. Never raises.
    """
    return _looked_up(round(latitude, 4), round(longitude, 4), base_url, user_agent)


@lru_cache(maxsize=512)
def _looked_up(latitude: float, longitude: float, base_url: str, user_agent: str) -> str | None:
    """The cached lookup.

    Keyed on the position rather than on a request object, so the cache is a small map of
    places to names. `place_name` rounds before calling this: a float that differs in its
    twelfth decimal place is the same place, and would otherwise be a cache miss for ever.

    Failures are cached too, and deliberately. A service that is down stays down for a
    while, and a retry on every upload would be a retry storm against a free service whose
    terms ask for one request a second.
    """
    try:
        response = httpx.get(
            base_url,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": _ZOOM,
            },
            headers={"User-Agent": user_agent},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        return _name_from(response.json())
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.warning("could not name the place at a coarse position: %s", exc)
        return None


def _name_from(body: object) -> str | None:
    """The most specific recognisable name in a reverse-geocoding response."""
    if not isinstance(body, dict):
        return None

    # **A position with nothing at it answers 200, not 404.** Verified against the live
    # service: the middle of the North Sea comes back as `{"error": "Unable to geocode"}`
    # with a perfectly successful status. An adapter that trusted the status code would
    # carry that object into the parser and hand back whatever fell out.
    if body.get("error"):
        logger.debug("nothing at that position: %s", body["error"])
        return None

    address = body.get("address")
    if isinstance(address, dict):
        for field in _PLACE_FIELDS:
            value = address.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    # No structured address, but a rendered one. Its first component is the most specific
    # thing the service found, which at this zoom is a place rather than a building.
    display = body.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.split(",")[0].strip()

    return None


def forget() -> None:
    """Empty the cache. For tests, and for a process that has been running a long time."""
    _looked_up.cache_clear()
