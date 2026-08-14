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

from agent.schemas import ProfileUpdate
from data.db import transaction
from data.repositories.profile import ProfileFact, ProfileRepository

logger = logging.getLogger(__name__)

MAX_INJECTED_FACTS = 30
MIN_INJECTED_CONFIDENCE = 0.5
CONFIDENCE_CAP = 0.95
CONFIRM_STEP = 0.1
INITIAL_CONFIDENCE = {"stated": 0.8, "inferred": 0.5}

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
