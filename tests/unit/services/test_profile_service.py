"""Unit tests for profile rendering and reconciliation. No model calls."""

import sqlite3
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


def test_learning_from_a_diagnosis_stores_what_the_model_returns(db, now):
    from tests.fakes.chat_models import ScriptedStructuredModel

    model = ScriptedStructuredModel(
        [
            ProfileUpdate(
                added=[ExtractedFact(fact="lives in Berlin", source="stated", confidence=0.9)]
            )
        ]
    )
    service = ProfileService(repo=ProfileRepository(db), gate_model=model, now=now)

    service.learn_from_diagnosis(
        answers={"watering": "twice a week on a schedule"}, location_text="Berlin"
    )

    assert [f.fact for f in ProfileRepository(db).list_all()] == ["lives in Berlin"]


def test_the_owners_answers_reach_the_model(db, now):
    from tests.fakes.chat_models import ScriptedStructuredModel

    model = ScriptedStructuredModel([ProfileUpdate()])
    service = ProfileService(repo=ProfileRepository(db), gate_model=model, now=now)

    service.learn_from_diagnosis(
        answers={"watering": "twice a week on a schedule"}, location_text=None
    )

    sent = str(model.prompts[0])
    assert "twice a week on a schedule" in sent


def test_the_current_profile_is_sent_so_the_model_can_echo_it_verbatim(db, now):
    """Reconciliation only deduplicates if the model sees the existing wording."""
    from data.db import transaction
    from tests.fakes.chat_models import ScriptedStructuredModel

    repo = ProfileRepository(db)
    with transaction(db):
        repo.upsert(fact="tends to overwater", source="inferred", confidence=0.6, now=now())

    model = ScriptedStructuredModel([ProfileUpdate()])
    ProfileService(repo=repo, gate_model=model, now=now).learn_from_diagnosis(
        answers={"watering": "daily"}, location_text=None
    )

    assert "tends to overwater" in str(model.prompts[0])


def test_a_failing_extraction_leaves_the_profile_untouched(db, now):
    """Extraction is best-effort: the diagnosis is already committed by now."""
    from tests.fakes.chat_models import FailingChatModel

    service = ProfileService(
        repo=ProfileRepository(db), gate_model=FailingChatModel(RuntimeError("boom")), now=now
    )

    # must not raise
    service.learn_from_diagnosis(answers={"watering": "daily"}, location_text=None)

    assert ProfileRepository(db).list_all() == []


def test_a_failing_extraction_reports_failure_to_its_caller(db, now):
    """`_learn` returns False so `learn_from_chat` knows not to advance its cursor."""
    from tests.fakes.chat_models import FailingChatModel

    service = ProfileService(
        repo=ProfileRepository(db), gate_model=FailingChatModel(RuntimeError("boom")), now=now
    )

    assert service._learn("some material") is False


def test_an_empty_update_still_counts_as_a_successful_round(db, now):
    """Material genuinely containing no fact must not be re-read forever."""
    from tests.fakes.chat_models import ScriptedStructuredModel

    service = ProfileService(
        repo=ProfileRepository(db), gate_model=ScriptedStructuredModel([ProfileUpdate()]), now=now
    )

    assert service._learn("nothing durable here") is True


def test_a_diagnosis_with_no_answers_makes_no_model_call(db, now):
    """Nothing the owner said means nothing to learn — do not pay for a call."""
    from tests.fakes.chat_models import ScriptedStructuredModel

    model = ScriptedStructuredModel([])
    service = ProfileService(repo=ProfileRepository(db), gate_model=model, now=now)

    service.learn_from_diagnosis(answers={}, location_text=None)

    assert model.call_count == 0


class _UpsertFailingRepository(ProfileRepository):
    """A repository whose write half breaks, independent of the model."""

    def upsert(self, **kwargs) -> None:
        raise sqlite3.OperationalError("database is locked")


def test_a_failing_apply_also_reports_failure_and_touches_nothing(db, now):
    """The failure need not originate in the model: applying a well-formed update
    can itself fail (a locked file, a constraint violation). That must be caught
    too, not just a failure from ``invoke_structured`` — otherwise a database error
    escapes a method whose whole contract is to never break its caller."""
    from tests.fakes.chat_models import ScriptedStructuredModel

    model = ScriptedStructuredModel(
        [
            ProfileUpdate(
                added=[ExtractedFact(fact="lives in Berlin", source="stated", confidence=0.9)]
            )
        ]
    )
    service = ProfileService(repo=_UpsertFailingRepository(db), gate_model=model, now=now)

    assert service._learn("some material") is False
    assert ProfileRepository(db).list_all() == []
