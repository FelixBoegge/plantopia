"""Reads and writes the researched species care profiles.

Deliberately unlike every other repository here: no ``user_id`` on any method, because the
table holds facts about species rather than records about people. `SpeciesCareProfile`'s
docstring carries that argument; `data/repositories/_ownership.py` is not imported for the
same reason, and its absence is the point rather than an oversight.

Only ever holds researched profiles. The hand-written tier lives in `tools/care_profiles.py`
and always wins, so nothing stored here can shadow a curated entry.
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agent.schemas import CareOrigin, CareProfile
from data.models import SpeciesCareProfile


def normalise(species: str) -> str:
    """The key a species is stored and found under.

    The same lowercase-and-strip `tools/care_profiles.lookup_plant_care_profile` already
    does, so that a name matching a curated profile matches a stored one identically. If the
    two ever disagreed, a species could be curated by one spelling and researched by another
    and the trusted tier would stop winning.
    """
    return species.strip().lower()


class CareProfileRepository:
    """Write methods do not commit; the caller groups writes with ``data.engine.transaction``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, species: str) -> CareProfile | None:
        """The stored profile for a species, or ``None``.

        ``None`` is a normal outcome and always has been — the caller widens its differential
        and lowers its confidence rather than failing.
        """
        key = normalise(species)
        if not key:
            return None

        row = self._session.scalar(
            select(SpeciesCareProfile).where(SpeciesCareProfile.species_key == key)
        )
        return _to_profile(row) if row else None

    def put(self, profile: CareProfile, *, now: datetime) -> None:
        """Record a researched profile.

        Refuses to store anything claiming to be curated. The curated tier is a Python dict
        that always wins, so a row here labelled curated could never be reached — it would be
        a lie in the database that no read could expose.

        Upserts rather than inserts. Two runs can research the same species concurrently: the
        lookup finds nothing, both research, both write. The second write is the same fact as
        the first, so last-one-wins is correct and a unique-violation would fail a diagnosis
        over a race that produced the right answer twice.
        """
        if profile.origin is not CareOrigin.RESEARCHED:
            raise ValueError(
                f"only researched profiles are stored here, not {profile.origin.value!r} — "
                "the curated tier is a Python dict and always wins"
            )

        low, high = profile.temperature_c
        values = {
            "species_key": normalise(profile.species),
            "species": profile.species.strip(),
            "light": profile.light,
            "water": profile.water,
            "temperature_min_c": low,
            "temperature_max_c": high,
            "humidity": profile.humidity,
            "sources_json": json.dumps(list(profile.sources)),
            "created_at": now,
        }
        statement = insert(SpeciesCareProfile).values(**values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[SpeciesCareProfile.species_key],
                set_={key: values[key] for key in values if key != "species_key"},
            )
        )


def _to_profile(row: SpeciesCareProfile) -> CareProfile:
    return CareProfile(
        species=row.species,
        light=row.light,
        water=row.water,
        temperature_c=(row.temperature_min_c, row.temperature_max_c),
        humidity=row.humidity,
        # Set rather than defaulted. Everything in this table was researched, and relying on
        # the schema default would mean a stored guess reading back as a curated fact.
        origin=CareOrigin.RESEARCHED,
        sources=json.loads(row.sources_json),
    )
