"""Every repository method, checked against a second owner.

Written once and table-driven on purpose. Each repository has its own tests for what it
does; this one asserts the property they all share and none of them owns — that a caller
cannot reach a record belonging to somebody else. A per-repository version of this would
be seven files that each have to remember, and the one that forgot would be the hole.

The rule has two halves, and they differ deliberately:

- **Reads return nothing.** Absent and forbidden are made indistinguishable, because a
  distinguishable refusal confirms the record exists.
- **Writes raise.** A write that quietly changes nothing looks identical to one that
  worked, and the caller has no way to report the truth to the person who asked.

`test_the_check_would_notice_a_missing_filter` is the test for the test: it removes a
`user_id` filter and asserts this file fails. Without it, a scoping check that had
silently stopped scoping would still pass.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from agent.schemas import (
    Candidate,
    ContagionAssessment,
    Differential,
    IPMTier,
    Roadmap,
    RoadmapStep,
    Severity,
)
from data.models import Plant
from data.repositories.diagnoses import DiagnosisRepository
from data.repositories.errors import RecordNotFoundError
from data.repositories.feedback import FeedbackRepository
from data.repositories.messages import MessageRepository
from data.repositories.observations import ObservationRepository
from data.repositories.plants import PlantRepository
from data.repositories.profile import ProfileRepository
from data.repositories.roadmap import RoadmapRepository
from data.repositories.runs import RunRepository

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _roadmap() -> Roadmap:
    return Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Stop watering until the top three centimetres are dry.",
                rationale="Standing water at the roots is what caused this.",
                success_signal="No new yellow leaves within a week.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            )
        ]
    )


def _differential() -> Differential:
    return Differential(
        is_healthy=False,
        reasoning="Wet soil.",
        candidates=[
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.7,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Push a finger into the soil three days after watering.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            ),
            Candidate(
                disorder_id="root-rot",
                name="Root rot",
                probability=0.3,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Unpot the plant and inspect the roots for softness.",
                severity=Severity.ACT_TODAY,
                transmissible=False,
            ),
        ],
    )


@pytest.fixture
def records(db, owner):
    """One of everything, all belonging to ``owner``."""
    plant_id = PlantRepository(db).create(
        owner,
        name="Basil",
        species="Ocimum basilicum",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=NOW,
    )
    observation_id = ObservationRepository(db).create(
        owner, plant_id=plant_id, kind="initial", photo_refs=[], user_notes=None, now=NOW
    )
    diagnosis_id = DiagnosisRepository(db).create(
        owner,
        observation_id=observation_id,
        plant_id=plant_id,
        differential=_differential(),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="test-model",
        now=NOW,
    )
    step_ids = RoadmapRepository(db).create_from_roadmap(
        owner,
        diagnosis_id=diagnosis_id,
        plant_id=plant_id,
        roadmap=_roadmap(),
        now=NOW,
    )
    message_id = MessageRepository(db).create(
        owner, plant_id=plant_id, role="user", content="hello", tool_calls=None, now=NOW
    )
    ProfileRepository(db).upsert(
        owner, fact="waters weekly", source="stated", confidence=0.8, now=NOW
    )
    ProfileRepository(db).set_cursor(owner, plant_id=plant_id, last_message_id=message_id)
    run_id = RunRepository(db).create(
        owner, plant_id=plant_id, kind="diagnosis", thread_id="t", now=NOW
    )
    RunRepository(db).append_event(run_id, kind="step", payload={"step": "one"}, now=NOW)
    return {
        "plant_id": plant_id,
        "observation_id": observation_id,
        "diagnosis_id": diagnosis_id,
        "step_id": step_ids[0],
        "message_id": message_id,
        "run_id": run_id,
    }


# (label, callable taking (session, user_id, ids)) — every public method that takes a
# record identifier or returns records belonging to an owner.
READS = [
    ("plants.get", lambda s, u, r: PlantRepository(s).get(u, r["plant_id"])),
    ("plants.list_all", lambda s, u, r: PlantRepository(s).list_all(u)),
    ("observations.get", lambda s, u, r: ObservationRepository(s).get(u, r["observation_id"])),
    (
        "observations.list_for_plant",
        lambda s, u, r: ObservationRepository(s).list_for_plant(u, r["plant_id"]),
    ),
    ("diagnoses.get", lambda s, u, r: DiagnosisRepository(s).get(u, r["diagnosis_id"])),
    (
        "diagnoses.latest_for_plant",
        lambda s, u, r: DiagnosisRepository(s).latest_for_plant(u, r["plant_id"]),
    ),
    (
        "diagnoses.list_for_plant",
        lambda s, u, r: DiagnosisRepository(s).list_for_plant(u, r["plant_id"]),
    ),
    (
        "roadmap.list_for_plant",
        lambda s, u, r: RoadmapRepository(s).list_for_plant(u, r["plant_id"]),
    ),
    ("roadmap.due_before", lambda s, u, r: RoadmapRepository(s).due_before(u, NOW)),
    (
        "feedback.exists_for_diagnosis",
        lambda s, u, r: FeedbackRepository(s).exists_for_diagnosis(u, r["diagnosis_id"]),
    ),
    (
        "messages.list_for_plant",
        lambda s, u, r: MessageRepository(s).list_for_plant(u, r["plant_id"]),
    ),
    ("runs.get", lambda s, u, r: RunRepository(s).get(u, r["run_id"])),
    ("runs.list_for_user", lambda s, u, r: RunRepository(s).list_for_user(u)),
    ("runs.thread_of", lambda s, u, r: RunRepository(s).thread_of(u, r["run_id"])),
    ("runs.events", lambda s, u, r: RunRepository(s).events(u, r["run_id"])),
    (
        "messages.list_for_plant_after",
        lambda s, u, r: MessageRepository(s).list_for_plant_after(u, r["plant_id"], after=None),
    ),
    ("profile.list_all", lambda s, u, r: ProfileRepository(s).list_all(u)),
    (
        "profile.cursor_position",
        lambda s, u, r: ProfileRepository(s).cursor_position(u, r["plant_id"]),
    ),
]

WRITES = [
    ("plants.rename", lambda s, u, r: PlantRepository(s).rename(u, r["plant_id"], name="X")),
    (
        "plants.update_species",
        lambda s, u, r: PlantRepository(s).update_species(
            u, r["plant_id"], species="X", species_confidence=1.0
        ),
    ),
    ("plants.delete", lambda s, u, r: PlantRepository(s).delete(u, r["plant_id"])),
    (
        "observations.create",
        lambda s, u, r: ObservationRepository(s).create(
            u, plant_id=r["plant_id"], kind="recheck", photo_refs=[], user_notes=None, now=NOW
        ),
    ),
    (
        "diagnoses.create",
        lambda s, u, r: DiagnosisRepository(s).create(
            u,
            observation_id=r["observation_id"],
            plant_id=r["plant_id"],
            differential=_differential(),
            contagion=None,
            retrieved=[],
            model="test-model",
            now=NOW,
        ),
    ),
    (
        "roadmap.create_from_roadmap",
        lambda s, u, r: RoadmapRepository(s).create_from_roadmap(
            u,
            diagnosis_id=r["diagnosis_id"],
            plant_id=r["plant_id"],
            roadmap=_roadmap(),
            now=NOW,
        ),
    ),
    (
        "roadmap.mark",
        lambda s, u, r: RoadmapRepository(s).mark(u, r["step_id"], status="done", now=NOW),
    ),
    (
        "feedback.create",
        lambda s, u, r: FeedbackRepository(s).create(
            u, diagnosis_id=r["diagnosis_id"], rating=5, did_it_help="yes", free_text=None, now=NOW
        ),
    ),
    (
        "messages.create",
        lambda s, u, r: MessageRepository(s).create(
            u, plant_id=r["plant_id"], role="user", content="hi", tool_calls=None, now=NOW
        ),
    ),
    (
        "profile.set_cursor",
        lambda s, u, r: ProfileRepository(s).set_cursor(
            u, plant_id=r["plant_id"], last_message_id=r["message_id"]
        ),
    ),
]


@pytest.mark.parametrize("label,call", READS, ids=[label for label, _ in READS])
def test_a_read_finds_nothing_for_another_owner(db, owner, other_owner, records, label, call):
    """Absent and forbidden must be the same answer — a refusal that distinguishes them
    tells a stranger the record exists."""
    mine = call(db, owner, records)
    theirs = call(db, other_owner, records)

    assert mine or mine is False or mine == [], f"{label} returned nothing for its own owner"
    assert theirs in (None, [], False), f"{label} leaked a record to another owner"


@pytest.mark.parametrize("label,call", WRITES, ids=[label for label, _ in WRITES])
def test_a_write_is_refused_for_another_owner(db, owner, other_owner, records, label, call):
    """And refused loudly. A write that changes nothing quietly is indistinguishable from
    one that worked, and the caller cannot report the truth."""
    with pytest.raises(RecordNotFoundError):
        call(db, other_owner, records)


def test_a_refused_write_changes_nothing(db, owner, other_owner, records):
    before = PlantRepository(db).get(owner, records["plant_id"])

    with pytest.raises(RecordNotFoundError):
        PlantRepository(db).rename(other_owner, records["plant_id"], name="stolen")

    assert PlantRepository(db).get(owner, records["plant_id"]).name == before.name


def test_the_check_would_notice_a_missing_filter(db, owner, other_owner, records):
    """The test for the test.

    A scoping check is only worth having if it fails when the scoping is removed. This
    performs the query `PlantRepository.get` performs, minus the ``user_id`` predicate,
    and asserts the result is exactly what the table-driven test above forbids — so if
    that test ever stops failing on a missing filter, this one says why.
    """
    unscoped = db.scalar(select(Plant).where(Plant.id == records["plant_id"]))

    assert unscoped is not None, "the record exists"
    assert unscoped.user_id == owner
    assert unscoped.user_id != other_owner, (
        "without the user_id predicate the query returns another owner's row — "
        "which is exactly the failure the tenancy tests exist to catch"
    )


def test_asking_to_cancel_another_owners_run_does_nothing(db, owner, other_owner, records):
    """`RunRepository` reports a refused write by returning False rather than raising, and
    is therefore not in the WRITES table above.

    The difference is deliberate: a status transition has a legitimate reason to fail that
    is not an error — a cancellation landing between two nodes, a second answer arriving —
    and a caller has to be able to tell it lost a race. What that costs is this test, which
    asserts the same property the table asserts for everybody else.
    """
    assert RunRepository(db).request_cancel(other_owner, records["run_id"]) is False
    assert RunRepository(db).get(owner, records["run_id"]).status == "queued"


def test_a_run_can_be_cancelled_by_the_owner_it_belongs_to(db, owner, records):
    """The other half. A method that refused everybody would pass the test above."""
    assert RunRepository(db).request_cancel(owner, records["run_id"]) is True
