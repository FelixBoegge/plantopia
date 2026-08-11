"""Render tests for the standalone UI components.

These drive ``render_differential`` and ``render_roadmap`` directly through
``AppTest.from_function`` rather than the full wizard, so each branch — healthy,
low-confidence, transmissible, no-plan — can be exercised in isolation with a
purpose-built schema instance instead of routing everything through one scripted
pipeline run.
"""

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.ui


def _render_differential_script(differential, *, low_confidence: bool) -> None:
    from ui.components.differential import render_differential

    render_differential(differential, low_confidence=low_confidence)


def _render_roadmap_script(roadmap) -> None:
    from ui.components.roadmap import render_roadmap

    render_roadmap(roadmap)


def test_render_differential_healthy_shows_success_not_a_conclusion():
    """A healthy finding is a valid outcome, not the absence of one."""
    from agent.schemas import Differential

    healthy = Differential(
        is_healthy=True, candidates=[], reasoning="No symptoms consistent with a disorder."
    )

    at = AppTest.from_function(
        _render_differential_script, args=(healthy,), kwargs={"low_confidence": False}
    )
    at.run()

    assert not at.exception
    assert any("looks healthy" in s.value for s in at.success)
    # No candidate cards and no "cannot tell" warning for a healthy result.
    assert not at.subheader
    assert not at.warning


def test_render_differential_low_confidence_shows_cannot_tell_warning():
    """Below the confidence threshold, the page must warn rather than assert a winner.

    This differential also carries one transmissible candidate with no contradicting
    evidence and one non-transmissible candidate that does have contradicting
    evidence, so both branches of the evidence rendering are exercised alongside the
    warning.
    """
    from agent.schemas import Candidate, Differential, Severity

    low_confidence = Differential(
        is_healthy=False,
        reasoning="Evidence does not clearly separate these two.",
        candidates=[
            Candidate(
                disorder_id="spider-mites",
                name="Spider mites",
                probability=0.4,
                supporting_evidence=["fine webbing"],
                contradicting_evidence=[],
                distinguishing_test="Tap a leaf over white paper and look for moving specks.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=True,
            ),
            Candidate(
                disorder_id="nutrient-deficiency",
                name="Nutrient deficiency",
                probability=0.35,
                supporting_evidence=["interveinal yellowing"],
                contradicting_evidence=["no webbing observed"],
                distinguishing_test="Check the oldest leaves first for the yellowing pattern.",
                severity=Severity.MONITOR,
                transmissible=False,
            ),
        ],
    )

    at = AppTest.from_function(
        _render_differential_script, args=(low_confidence,), kwargs={"low_confidence": True}
    )
    at.run()

    assert not at.exception
    assert not at.success
    warnings = [w.value for w in at.warning]
    assert any("cannot tell you confidently" in w for w in warnings)
    # The transmissible candidate triggers its own, separate contagion-style warning.
    assert any("can spread to nearby plants" in w for w in warnings)
    # The candidate with no contradicting evidence gets the explicit fallback caption.
    captions = [c.value for c in at.caption]
    assert any("Nothing observed argues against this" in c for c in captions)
    # The candidate that does have contradicting evidence renders it as a bullet.
    markdown_text = [m.value for m in at.markdown]
    assert any("no webbing observed" in m for m in markdown_text)
    # Both candidates are headed, the first one flagged as most likely.
    headings = [s.value for s in at.subheader]
    assert any("Spider mites" in h and "most likely" in h for h in headings)
    assert any("Nutrient deficiency" in h and "most likely" not in h for h in headings)


def test_render_roadmap_with_no_plan_shows_the_no_plan_message():
    """``build_roadmap`` can legitimately leave the roadmap unset; say so plainly."""
    at = AppTest.from_function(_render_roadmap_script, args=(None,))
    at.run()

    assert not at.exception
    assert any("No treatment plan was produced" in i.value for i in at.info)
    assert not at.subheader


def test_render_roadmap_with_steps_shows_due_dates_today_and_later():
    """Steps due immediately and steps due later render distinct due-date text."""
    from agent.schemas import IPMTier, Roadmap, RoadmapStep

    roadmap = Roadmap(
        steps=[
            RoadmapStep(
                ordinal=1,
                action="Stop watering until the top 3 cm is dry.",
                rationale="Lets the roots breathe.",
                success_signal="No new yellow leaves.",
                tier=IPMTier.CULTURAL,
                day_offset=0,
            ),
            RoadmapStep(
                ordinal=2,
                action="Repot into a container with drainage holes.",
                rationale="Standing water at the roots caused this.",
                success_signal="Soil dries out within three days of watering.",
                tier=IPMTier.MECHANICAL,
                day_offset=3,
            ),
        ]
    )

    at = AppTest.from_function(_render_roadmap_script, args=(roadmap,))
    at.run()

    assert not at.exception
    assert any("Treatment plan" in s.value for s in at.subheader)
    captions = [c.value for c in at.caption]
    assert any("today" in c for c in captions)
    assert any("in 3 days" in c for c in captions)


def _render_timeline_script(detail) -> None:
    from ui.components.timeline import render_timeline

    render_timeline(detail)


def test_render_timeline_shows_every_diagnosis():
    from datetime import UTC, datetime

    from agent.schemas import Candidate, ContagionAssessment, Differential, Severity
    from data.repositories.diagnoses import DiagnosisRecord
    from data.repositories.observations import ObservationRecord
    from data.repositories.plants import PlantRecord
    from services.plant_service import PlantDetail

    plant = PlantRecord(
        id=1,
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    diagnosis = DiagnosisRecord(
        id=10,
        observation_id=1,
        plant_id=1,
        differential=Differential(
            is_healthy=False,
            reasoning="r",
            candidates=[
                Candidate(
                    disorder_id="d1",
                    name="Overwatering",
                    probability=0.7,
                    supporting_evidence=["e"],
                    contradicting_evidence=[],
                    distinguishing_test="Feel the soil after three days.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                ),
                Candidate(
                    disorder_id="d2",
                    name="Root rot",
                    probability=0.2,
                    supporting_evidence=["e2"],
                    contradicting_evidence=[],
                    distinguishing_test="Check roots for decay.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                ),
            ],
        ),
        contagion=ContagionAssessment(at_risk=False, advice="none"),
        retrieved=[],
        model="m",
        cost_usd=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    observation = ObservationRecord(
        id=1,
        plant_id=1,
        kind="initial",
        photo_refs=["img-1"],
        user_notes=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    detail = PlantDetail(
        plant=plant,
        observations=[observation],
        diagnoses=[diagnosis],
        roadmap_steps=[],
        feedback_due=False,
    )

    at = AppTest.from_function(_render_timeline_script, args=(detail,))
    at.run()

    assert not at.exception
    assert any("Overwatering" in m.value for m in at.markdown)


def test_render_timeline_with_no_diagnoses_says_so():
    from datetime import UTC, datetime

    from data.repositories.plants import PlantRecord
    from services.plant_service import PlantDetail

    plant = PlantRecord(
        id=2,
        name="New plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    detail = PlantDetail(
        plant=plant, observations=[], diagnoses=[], roadmap_steps=[], feedback_due=False
    )

    at = AppTest.from_function(_render_timeline_script, args=(detail,))
    at.run()

    assert not at.exception
    assert any("No diagnoses yet" in i.value for i in at.info)


def _render_checklist_script(steps) -> None:
    import streamlit as st

    from ui.components.roadmap_checklist import render_roadmap_checklist

    calls = st.session_state.setdefault("_mark_calls", [])
    render_roadmap_checklist(steps, on_mark=lambda step_id, status: calls.append((step_id, status)))


def test_checklist_renders_pending_and_done_steps_distinctly():
    from datetime import UTC, datetime

    from agent.schemas import IPMTier
    from data.repositories.roadmap import RoadmapStepRecord

    pending = RoadmapStepRecord(
        id=1,
        diagnosis_id=1,
        plant_id=1,
        ordinal=1,
        action="Stop watering.",
        rationale="r",
        success_signal="s",
        tier=IPMTier.CULTURAL,
        due_date=datetime(2026, 1, 1, tzinfo=UTC),
        status="pending",
        completed_at=None,
    )
    done = RoadmapStepRecord(
        id=2,
        diagnosis_id=1,
        plant_id=1,
        ordinal=2,
        action="Repot.",
        rationale="r",
        success_signal="s",
        tier=IPMTier.MECHANICAL,
        due_date=datetime(2026, 1, 1, tzinfo=UTC),
        status="done",
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    at = AppTest.from_function(_render_checklist_script, args=([pending, done],))
    at.run()

    assert not at.exception
    assert len(at.checkbox) == 2
    assert at.checkbox[0].value is False
    assert at.checkbox[1].value is True


def test_ticking_a_pending_step_calls_on_mark():
    from datetime import UTC, datetime

    from agent.schemas import IPMTier
    from data.repositories.roadmap import RoadmapStepRecord

    pending = RoadmapStepRecord(
        id=1,
        diagnosis_id=1,
        plant_id=1,
        ordinal=1,
        action="Stop watering.",
        rationale="r",
        success_signal="s",
        tier=IPMTier.CULTURAL,
        due_date=datetime(2026, 1, 1, tzinfo=UTC),
        status="pending",
        completed_at=None,
    )

    at = AppTest.from_function(_render_checklist_script, args=([pending],))
    at.run()
    at.checkbox[0].check().run()

    assert at.session_state["_mark_calls"] == [(1, "done")]
