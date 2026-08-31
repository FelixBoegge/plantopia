"""Baseline care requirements per species.

This grounds the question "is this normal for this plant?". A fern dropping fronds
in dry air is a different situation from a succulent doing the same thing.

Three tiers, in order: the hand-written table below, then profiles researched for species
it does not cover, then researching one. The hand-written tier **always wins** — everything
behind it is a guess a model made from search results, and a guess that can displace a known
answer turns a reliable lookup into an unreliable one for the cases that used to work.
"""

from collections.abc import Callable

from agent.schemas import CareProfile

_PROFILES: dict[str, CareProfile] = {
    "basil": CareProfile(
        species="Basil",
        light="Six or more hours of direct sun",
        water="Keep evenly moist; do not let it wilt",
        temperature_c=(18, 30),
        humidity="Average indoor humidity is fine",
    ),
    "monstera": CareProfile(
        species="Monstera deliciosa",
        light="Bright indirect light; no harsh direct sun",
        water="Water when the top 3 cm of soil is dry",
        temperature_c=(18, 27),
        humidity="Prefers above 50 percent",
    ),
    "fiddle leaf fig": CareProfile(
        species="Ficus lyrata",
        light="Bright indirect light, tolerates some direct morning sun",
        water="Water when the top 5 cm is dry; dislikes sitting wet",
        temperature_c=(16, 24),
        humidity="Prefers above 40 percent",
    ),
    "snake plant": CareProfile(
        species="Dracaena trifasciata",
        light="Tolerates low light, grows faster in bright indirect",
        water="Water sparingly; let the soil dry completely",
        temperature_c=(15, 29),
        humidity="Tolerates dry air",
    ),
    "peace lily": CareProfile(
        species="Spathiphyllum",
        light="Medium to low indirect light",
        water="Keep lightly moist; wilts dramatically then recovers",
        temperature_c=(18, 27),
        humidity="Prefers above 50 percent",
    ),
    "boston fern": CareProfile(
        species="Nephrolepis exaltata",
        light="Bright indirect light, no direct sun",
        water="Keep consistently moist, never soggy",
        temperature_c=(16, 24),
        humidity="Needs above 60 percent",
    ),
    "tomato": CareProfile(
        species="Solanum lycopersicum",
        light="Eight or more hours of direct sun",
        water="Deep, regular watering; inconsistency causes blossom end rot",
        temperature_c=(18, 29),
        humidity="Average; good airflow matters more",
    ),
    "pothos": CareProfile(
        species="Epipremnum aureum",
        light="Low to bright indirect light",
        water="Water when the top 3 cm is dry",
        temperature_c=(17, 29),
        humidity="Average indoor humidity is fine",
    ),
}

_ALIASES: dict[str, str] = {
    "ocimum basilicum": "basil",
    "monstera deliciosa": "monstera",
    "swiss cheese plant": "monstera",
    "ficus lyrata": "fiddle leaf fig",
    "dracaena trifasciata": "snake plant",
    "sansevieria": "snake plant",
    "spathiphyllum": "peace lily",
    "nephrolepis exaltata": "boston fern",
    "solanum lycopersicum": "tomato",
    "epipremnum aureum": "pothos",
    "devil's ivy": "pothos",
}


def lookup_plant_care_profile(species: str) -> CareProfile | None:
    """Return the *hand-written* care requirements for a species, or None if unknown.

    Matching is case-insensitive and accepts common or scientific names. An unknown
    species is a normal outcome, not an error — the caller widens the differential
    and lowers confidence instead.

    This is the trusted tier on its own. `make_care_profile_lookup` is what the graph gets;
    it consults this first and never overrides it.
    """
    key = species.strip().lower()
    if not key:
        return None
    key = _ALIASES.get(key, key)
    return _PROFILES.get(key)


def make_care_profile_lookup(
    *,
    stored: Callable[[str], CareProfile | None] | None = None,
    research: Callable[[str], CareProfile | None] | None = None,
) -> Callable[[str], CareProfile | None]:
    """The lookup the graph is given: curated, then stored, then researched.

    A factory rather than a function because the tiers behind the first need a database
    session and a model, and `tools/` holds neither. The port's shape is unchanged — callers
    still pass a species and get a profile or ``None``.

    Both tiers are optional and default to absent, which yields exactly today's behaviour.
    That is what lets the stored tier land before anything researches, and what lets the
    evaluation harness leave the research tier off without a special case.

    Every failure behind the curated tier degrades to ``None``, which is the outcome every
    caller has always handled: an unknown species widens the differential and lowers
    confidence rather than failing a run.
    """

    def lookup(species: str) -> CareProfile | None:
        curated = lookup_plant_care_profile(species)
        if curated is not None:
            return curated

        if not species.strip():
            return None

        for tier in (stored, research):
            if tier is None:
                continue
            found = tier(species)
            if found is not None:
                return found

        return None

    return lookup
