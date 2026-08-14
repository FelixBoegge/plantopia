"""The learned user profile: what the agent remembers about the owner.

Extraction is best-effort and always runs *after* the work it learns from has
been committed, so a failure here can never cost someone their diagnosis
(spec §6).

``render_facts`` is a module-level function rather than a method because the
evaluation harness renders a fixture profile without a database (spec §4.3).
"""

import logging
from collections.abc import Callable
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompts.profile import EXTRACT_PROFILE
from agent.schemas import ProfileUpdate
from agent.structured import StructuredOutputFailed, invoke_structured
from data.db import transaction
from data.repositories.messages import MessageRepository
from data.repositories.profile import ProfileFact, ProfileRepository

logger = logging.getLogger(__name__)

MAX_INJECTED_FACTS = 30
MIN_INJECTED_CONFIDENCE = 0.5
CONFIDENCE_CAP = 0.95
CONFIRM_STEP = 0.1
INITIAL_CONFIDENCE = {"stated": 0.8, "inferred": 0.5}
CHAT_TURNS_PER_EXTRACTION = 4

_HEADER = """What we believe about this owner — background only, possibly outdated.
The photograph, the symptoms and the owner's answers about THIS plant always
take precedence. Do not let a prior about past habits override evidence in front
of you; if they conflict, say so in your reasoning."""


def render_facts(facts: list[ProfileFact]) -> str:
    """Render facts as a prompt block, or the empty string when there are none.

    Empty means empty: no header, no placeholder. A section that describes itself
    and is then blank invites the model to fill the silence, which is exactly how
    the fabricated-evidence bug in ``known-limitations.md`` happened.
    """
    if not facts:
        return ""
    lines = "\n".join(f"- {f.fact} (confidence {f.confidence:.1f})" for f in facts)
    return f"{_HEADER}\n\n{lines}"


class ProfileService:
    """Maintains and renders the owner's profile."""

    def __init__(
        self,
        *,
        repo: ProfileRepository,
        gate_model: BaseChatModel,
        now: Callable[[], datetime],
    ) -> None:
        self._repo = repo
        self._gate_model = gate_model
        self._now = now

    def facts_for_prompt(self) -> str:
        """The block injected into the diagnosis and chat prompts."""
        facts = [f for f in self._repo.list_all() if f.confidence >= MIN_INJECTED_CONFIDENCE]
        return render_facts(facts[:MAX_INJECTED_FACTS])

    def all_facts(self) -> list[ProfileFact]:
        """Every fact, unfiltered — the view shows low-confidence ones too."""
        return self._repo.list_all()

    def forget(self, fact: str) -> None:
        """Delete a fact the owner says is wrong. The only correction mechanism
        besides the reconciliation loop superseding a fact on its own."""
        with transaction(self._repo.connection):
            self._repo.supersede(fact)

    def apply_update(self, update: ProfileUpdate) -> None:
        """Apply a reconciliation, dropping anything that does not match stored text.

        ``confirmed`` and ``superseded`` are validated against what is actually
        stored. A model must not be able to insert a fact through the confirmation
        channel — which would skip the confidence policy — nor delete a real fact
        by hallucinating near-miss text.
        """
        known = {f.fact: f for f in self._repo.list_all()}
        now = self._now()

        with transaction(self._repo.connection):
            for fact in update.confirmed:
                existing = known.get(fact)
                if existing is None:
                    logger.info("dropping confirmation of an unknown fact: %r", fact)
                    continue
                self._repo.upsert(
                    fact=fact,
                    source=existing.source,
                    confidence=min(existing.confidence + CONFIRM_STEP, CONFIDENCE_CAP),
                    now=now,
                )

            for candidate in update.added:
                if candidate.fact in known:
                    continue
                self._repo.upsert(
                    fact=candidate.fact,
                    source=candidate.source,
                    confidence=INITIAL_CONFIDENCE[candidate.source],
                    now=now,
                )

            for fact in update.superseded:
                if fact not in known:
                    logger.info("dropping supersession of an unknown fact: %r", fact)
                    continue
                self._repo.supersede(fact)

    def learn_from_diagnosis(self, *, answers: dict[str, str], location_text: str | None) -> None:
        """Extract durable facts from what the owner said during a diagnosis.

        The clarifying answers are the highest-signal text in the application —
        the owner literally answering how often they water. Called after the
        diagnosis is committed, so a failure here is invisible to them.
        """
        if not answers:
            return

        material = "\n".join(f"- {key}: {value}" for key, value in answers.items())
        if location_text:
            material = f"Stated location: {location_text}\n{material}"

        self._learn(material)

    def learn_from_chat(self, plant_id: int, messages: MessageRepository) -> None:
        """Extract from this plant's chat thread, reading only what is new.

        Chat has no natural session boundary, so extraction fires every
        ``CHAT_TURNS_PER_EXTRACTION`` owner turns over just the turns since the
        cursor. Cost per turn stays flat instead of growing with thread length —
        the failure mode ``M16`` records for chat context itself.
        """
        cursor = self._repo.cursor_for(plant_id) or 0
        new = [m for m in messages.list_for_plant(plant_id) if m.id > cursor and m.role == "user"]
        if len(new) < CHAT_TURNS_PER_EXTRACTION:
            return

        material = "\n".join(f"- {m.content}" for m in new)
        if not self._learn(material):
            # Extraction failed. Leaving the cursor where it is means these turns are
            # read again next time rather than silently lost.
            return

        with transaction(self._repo.connection):
            self._repo.set_cursor(plant_id=plant_id, last_message_id=new[-1].id)

    def _learn(self, material: str) -> bool:
        """Run one extraction/reconciliation round over new material.

        Returns:
            ``True`` when a round completed and any update was applied — including
            an empty one, because material that genuinely held no durable fact has
            been dealt with and must not be re-read forever. ``False`` when extraction
            failed *or* when applying its result failed — either way nothing was
            durably written, which is what tells ``learn_from_chat`` to leave its
            cursor alone so those turns are retried.

        ``apply_update`` runs inside the same guarded region as the model call, not
        after it: it is the half that touches the database (a transaction, a run of
        ``upsert``/``supersede`` calls), and a locked file or constraint violation
        there is exactly the kind of failure this method exists to swallow. Letting
        it through the exception guard would have this "best-effort" extraction
        break its caller anyway — after the diagnosis it is learning from has
        already been committed and shown to the owner.
        """
        current = self._repo.list_all()
        profile_block = (
            "\n".join(f"- {f.fact}" for f in current) if current else "(the profile is empty)"
        )
        messages = [
            SystemMessage(EXTRACT_PROFILE),
            HumanMessage(f"Profile as it stands:\n{profile_block}\n\nNew material:\n{material}"),
        ]

        try:
            update = invoke_structured(self._gate_model, ProfileUpdate, messages)
            self.apply_update(update)
        except StructuredOutputFailed as exc:
            logger.warning("profile extraction failed: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 — the update round must never break its caller
            logger.warning(
                "profile update failed to apply (database or reconciliation error): %s", exc
            )
            return False

        return True
