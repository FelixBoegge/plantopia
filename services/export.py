"""Everything held about one person, in a file they can keep.

Consent that can be given and never inspected is not a control. Somebody who agreed to
photographs and text being sent to a model is entitled to see what accumulated as a result,
in a form that does not require this application to read.

So: JSON in a ZIP. JSON because it opens anywhere; a ZIP because the photographs are bytes
and one file is what somebody can keep.

**Names travel with identifiers.** An export whose records reference each other only by UUID
is complete and unreadable — a diagnosis that says `plant_id: 01a0…` tells a person nothing
about which plant it was. Each record carries the name of what it points at as well, which
costs a few bytes and is the difference between an archive and a receipt.

Built in memory rather than streamed. Streaming would mean holding a database session open
across the whole response for data bounded by one person's plants and an upload limit that is
already configuration — so this assembles, checks its size, and hands back bytes.
"""

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from core.blobs import BlobStore
from core.config import Settings
from data.models import User
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.errors import RecordNotFoundError
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from data.repositories.usage import UsageRepository

logger = logging.getLogger(__name__)

# What the archive calls the file a person opens first.
MANIFEST = "account.json"
PHOTOGRAPHS = "photographs"


class ExportTooLargeError(Exception):
    """The archive would exceed what this deployment is willing to build in memory."""


@dataclass(frozen=True, slots=True)
class Export:
    """The archive, and what to call it."""

    filename: str
    content: bytes


def build(
    session: Session,
    *,
    user_id: UUID,
    blobs: BlobStore,
    settings: Settings,
    now: datetime,
) -> Export:
    """Assemble everything this owner holds.

    Every read is owner-scoped through the repositories that already enforce it, so nothing
    belonging to anybody else can reach the archive — the same guarantee the endpoints have,
    from the same code.
    """
    user = session.get(User, user_id)
    if user is None:  # pragma: no cover — a session names an account that exists
        raise RecordNotFoundError("no such account")

    plants = PlantRepository(session).list_all(user_id)
    names = {plant.id: plant.name for plant in plants}

    observations = ObservationRepository(session)
    diagnoses = DiagnosisRepository(session)
    roadmap = RoadmapRepository(session)
    messages = MessageRepository(session)

    document = {
        "exported_at": now.isoformat(),
        "account": {
            "id": str(user.id),
            "email": user.email,
            "created_at": user.created_at.isoformat(),
            "tier": user.tier,
            "consent_version": user.consent_version,
            "consent_at": user.consent_at.isoformat() if user.consent_at else None,
        },
        "plants": [
            {
                "id": str(plant.id),
                "name": plant.name,
                "species": plant.species,
                "location_kind": plant.location_kind,
                "location_text": plant.location_text,
                "created_at": plant.created_at.isoformat(),
                "observations": [
                    _observation(record, names)
                    for record in observations.list_for_plant(user_id, plant.id)
                ],
                "diagnoses": [
                    _diagnosis(record, names)
                    for record in diagnoses.list_for_plant(user_id, plant.id)
                ],
                "treatment_steps": [
                    _step(record, names) for record in roadmap.list_for_plant(user_id, plant.id)
                ],
                "conversation": [
                    _message(record, names) for record in messages.list_for_plant(user_id, plant.id)
                ],
            }
            for plant in plants
        ],
        "learned_about_you": [
            {
                "fact": fact.fact,
                "source": fact.source,
                "confidence": fact.confidence,
                "first_seen": fact.first_seen.isoformat(),
                "last_confirmed": fact.last_confirmed.isoformat(),
            }
            for fact in ProfileRepository(session).list_all(user_id)
        ],
        "treatment_feedback": [
            {
                "diagnosis_id": str(row.diagnosis_id),
                "rating": row.rating,
                "did_it_help": row.did_it_help,
                "free_text": row.free_text,
                "created_at": row.created_at.isoformat(),
            }
            for row in FeedbackRepository(session).list_for_user(user_id)
        ],
        "usage": [
            {
                "kind": row.kind,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "cost_usd": row.cost_usd,
                "succeeded": row.succeeded,
                "occurred_at": row.occurred_at.isoformat(),
            }
            for row in UsageRepository(session).list_for_user(user_id)
        ],
    }

    return _archive(
        document, keys=_photograph_keys(document), blobs=blobs, user_id=user_id, settings=settings
    )


def _observation(record, names: dict[UUID, str]) -> dict:
    return {
        "id": str(record.id),
        "plant": names.get(record.plant_id),
        "kind": record.kind,
        "uploaded_at": record.created_at.isoformat(),
        "photographed_at": record.captured_at.isoformat() if record.captured_at else None,
        "position": (
            {"latitude": record.latitude, "longitude": record.longitude}
            if record.latitude is not None
            else None
        ),
        "notes": record.user_notes,
        "photographs": list(record.photo_refs),
        "weather": record.weather.model_dump(mode="json") if record.weather else None,
    }


def _diagnosis(record, names: dict[UUID, str]) -> dict:
    return {
        "id": str(record.id),
        # The name as well as the identifier. "Which plant was this about?" should not
        # require cross-referencing two files by hand.
        "plant": names.get(record.plant_id),
        "made_at": record.created_at.isoformat(),
        "healthy": record.differential.is_healthy,
        "reasoning": record.differential.reasoning,
        "candidates": [
            {
                "name": candidate.name,
                "probability": candidate.probability,
                "severity": candidate.severity.value,
                "supporting_evidence": list(candidate.supporting_evidence),
                "contradicting_evidence": list(candidate.contradicting_evidence),
                "distinguishing_test": candidate.distinguishing_test,
            }
            for candidate in record.differential.candidates
        ],
        "species_identified_by": record.species_method,
        "species_confirmed_by_you": record.species_confirmed,
    }


def _step(record, names: dict[UUID, str]) -> dict:
    return {
        "plant": names.get(record.plant_id),
        "diagnosis_id": str(record.diagnosis_id),
        "action": record.action,
        "rationale": record.rationale,
        "success_signal": record.success_signal,
        "due": record.due_date.isoformat(),
        "status": record.status,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


def _message(record, names: dict[UUID, str]) -> dict:
    return {
        "plant": names.get(record.plant_id),
        "who": record.role,
        "said": record.content,
        "consulted": record.tool_calls,
        "at": record.created_at.isoformat(),
    }


def _photograph_keys(document: dict) -> list[str]:
    """Every blob this owner's observations refer to, once each.

    Read back out of the assembled document rather than queried separately, so the archive
    cannot contain a photograph the manifest does not mention or vice versa.
    """
    seen: dict[str, None] = {}
    for plant in document["plants"]:
        for observation in plant["observations"]:
            for key in observation["photographs"]:
                seen[key] = None
    return list(seen)


def _archive(
    document: dict,
    *,
    keys: list[str],
    blobs: BlobStore,
    user_id: UUID,
    settings: Settings,
) -> Export:
    buffer = io.BytesIO()
    total = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(document, indent=2, ensure_ascii=False))

        for key in keys:
            data = blobs.get(user_id, UUID(key))
            if data is None:
                # A reference with no bytes behind it. Recorded rather than raised: an
                # export that fails because one photograph went missing is an export
                # somebody cannot have at all.
                logger.warning("a photograph referenced by an observation is missing")
                continue

            total += len(data)
            if total > settings.max_export_bytes:
                raise ExportTooLargeError(
                    "this account holds more than can be exported in one request"
                )
            archive.writestr(f"{PHOTOGRAPHS}/{key}", data)

    account_id = document["account"]["id"]
    return Export(filename=f"plantopia-export-{account_id}.zip", content=buffer.getvalue())
