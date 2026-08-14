"""Profile fixtures for the evaluation harness.

A profile is a run-level input, not a per-case one: it describes the owner, and
every case in a run shares it. Rendering goes through the production
``render_facts`` so the harness measures the block the application actually
injects, not a lookalike.
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml

from data.repositories.profile import ProfileFact
from services.profile_service import render_facts

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def load_profile(name: str, directory: Path) -> str:
    """Render a named fixture as the prompt block the pipeline would see.

    Raises:
        ValueError: if no fixture of that name exists.
    """
    path = directory / f"{name}.yaml"
    if not path.exists():
        raise ValueError(f"no evaluation profile named {name!r} in {directory}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    facts = [
        ProfileFact(
            fact=entry["fact"],
            source=entry["source"],
            confidence=float(entry["confidence"]),
            first_seen=_EPOCH,
            last_confirmed=_EPOCH,
        )
        for entry in raw.get("facts") or []
    ]
    return render_facts(facts)
