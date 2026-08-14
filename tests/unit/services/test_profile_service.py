"""Unit tests for profile rendering and reconciliation. No model calls."""

from datetime import UTC, datetime

from agent.schemas import ExtractedFact, ProfileUpdate
from data.db import transaction
from data.repositories.profile import ProfileFact, ProfileRepository
from services.profile_service import ProfileService, render_facts

WHEN = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _fact(text: str, confidence: float = 0.7, source: str = "inferred") -> ProfileFact:
    return ProfileFact(
        fact=text, source=source, confidence=confidence, first_seen=WHEN, last_confirmed=WHEN
    )


def _service(db, now) -> ProfileService:
    from tests.fakes.chat_models import ScriptedStructuredModel

    return ProfileService(
        repo=ProfileRepository(db), gate_model=ScriptedStructuredModel([]), now=now
    )


def test_an_empty_profile_renders_nothing_at_all():
    """Not an empty header. A section that announces itself and is then blank is
    what produced the fabricated-evidence bug in known-limitations.md."""
    assert render_facts([]) == ""


def test_a_populated_profile_renders_facts_with_confidence():
    block = render_facts([_fact("lives in Berlin", 0.9)])
    assert "lives in Berlin" in block
    assert "0.9" in block


def test_the_block_subordinates_priors_to_evidence():
    block = render_facts([_fact("tends to overwater")]).lower()
    assert "take precedence" in block or "takes precedence" in block


def test_low_confidence_facts_are_not_injected(db, now):
    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="weak guess", source="inferred", confidence=0.4, now=now())
        repo.upsert(fact="solid", source="stated", confidence=0.8, now=now())

    block = _service(db, now).facts_for_prompt()
    assert "solid" in block
    assert "weak guess" not in block


def test_at_most_thirty_facts_are_injected(db, now):
    repo = ProfileRepository(db)
    with transaction(db):
        for i in range(40):
            repo.upsert(fact=f"fact number {i}", source="inferred", confidence=0.6, now=now())

    block = _service(db, now).facts_for_prompt()
    assert block.count("fact number") == 30


def test_confirming_a_fact_raises_confidence_and_stamps_it(db, now):
    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.5, now=now())

    _service(db, now).apply_update(ProfileUpdate(confirmed=["tends to overwater"]))

    stored = repo.list_all()[0]
    assert stored.confidence == 0.6


def test_confidence_is_capped_below_certainty(db, now):
    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.95, now=now())

    _service(db, now).apply_update(ProfileUpdate(confirmed=["tends to overwater"]))

    assert repo.list_all()[0].confidence == 0.95


def test_added_facts_get_source_dependent_starting_confidence(db, now):
    _service(db, now).apply_update(
        ProfileUpdate(
            added=[
                ExtractedFact(fact="lives in Berlin", source="stated", confidence=0.99),
                ExtractedFact(fact="tends to overwater", source="inferred", confidence=0.99),
            ]
        )
    )

    stored = {f.fact: f.confidence for f in ProfileRepository(db).list_all()}
    assert stored["lives in Berlin"] == 0.8
    assert stored["tends to overwater"] == 0.5


def test_superseding_removes_a_contradicted_fact(db, now):
    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="lives in Berlin", source="stated", confidence=0.8, now=now())

    _service(db, now).apply_update(ProfileUpdate(superseded=["lives in Berlin"]))

    assert repo.list_all() == []


def test_confirming_an_unknown_fact_is_dropped_not_inserted(db, now):
    """A model must not be able to add a fact through the confirmation channel,
    where it would skip the confidence policy entirely."""
    _service(db, now).apply_update(ProfileUpdate(confirmed=["never observed"]))

    assert ProfileRepository(db).list_all() == []


def test_superseding_an_unknown_fact_cannot_delete_a_near_miss(db, now):
    """A hallucinated near-miss must not delete a real fact."""
    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.5, now=now())

    _service(db, now).apply_update(ProfileUpdate(superseded=["tends to over-water"]))

    assert [f.fact for f in repo.list_all()] == ["tends to overwater"]
