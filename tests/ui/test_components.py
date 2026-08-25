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


def _timeline_plant():
    from datetime import UTC, datetime

    from data.repositories.plants import PlantRecord

    return PlantRecord(
        id=1,
        name="Basil",
        species="Basil",
        species_confidence=0.9,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _timeline_diagnosis(diagnosis_id: int, observation_id: int, name: str, day: int):
    from datetime import UTC, datetime

    from agent.schemas import Candidate, ContagionAssessment, Differential, Severity
    from data.repositories.diagnoses import DiagnosisRecord

    return DiagnosisRecord(
        id=diagnosis_id,
        observation_id=observation_id,
        plant_id=1,
        differential=Differential(
            is_healthy=False,
            reasoning=f"reasoning for {name}",
            candidates=[
                Candidate(
                    disorder_id="d1",
                    name=name,
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
        token_usage=None,
        cost_usd=None,
        created_at=datetime(2026, 1, day, tzinfo=UTC),
    )


def _timeline_observation(observation_id: int, kind: str):
    from datetime import UTC, datetime

    from data.repositories.observations import ObservationRecord

    return ObservationRecord(
        id=observation_id,
        plant_id=1,
        kind=kind,
        photo_refs=["img-1"],
        user_notes=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_render_timeline_shows_every_diagnosis():
    """Two diagnoses, both rendered — a single-entry timeline could not tell an
    iterating renderer apart from one that only ever shows the newest."""
    from services.plant_service import PlantDetail

    detail = PlantDetail(
        plant=_timeline_plant(),
        observations=[_timeline_observation(1, "initial"), _timeline_observation(2, "initial")],
        diagnoses=[
            _timeline_diagnosis(11, 2, "Spider mites", day=8),
            _timeline_diagnosis(10, 1, "Overwatering", day=1),
        ],
        roadmap_steps=[],
        feedback_due=False,
    )

    at = AppTest.from_function(_render_timeline_script, args=(detail,))
    at.run()

    assert not at.exception
    markdown = [m.value for m in at.markdown]
    assert any("Overwatering" in m for m in markdown)
    assert any("Spider mites" in m for m in markdown)


def test_render_timeline_marks_a_recheck_distinctly_from_a_fresh_diagnosis(owner):
    """``persist`` records kind="recheck" vs "initial" on the observation, and the
    timeline iterated only over diagnoses — so a re-check's entry looked identical to a
    brand-new diagnosis and the recorded distinction never reached the owner, even
    though the chat agent's journal tool already read it."""
    from services.plant_service import PlantDetail
    from ui.components.timeline import _RECHECK_MARKER

    detail = PlantDetail(
        plant=_timeline_plant(),
        observations=[_timeline_observation(1, "initial"), _timeline_observation(2, "recheck")],
        diagnoses=[
            _timeline_diagnosis(11, 2, "Overwatering again", day=8),
            _timeline_diagnosis(10, 1, "Overwatering", day=1),
        ],
        roadmap_steps=[],
        feedback_due=False,
    )

    at = AppTest.from_function(_render_timeline_script, args=(detail,))
    at.run()

    assert not at.exception
    captions = [c.value for c in at.caption]
    # Exactly one of the two entries is marked: the one whose observation was a re-check.
    assert captions.count(_RECHECK_MARKER) == 1


def test_render_timeline_marks_nothing_when_every_observation_is_initial():
    from services.plant_service import PlantDetail
    from ui.components.timeline import _RECHECK_MARKER

    detail = PlantDetail(
        plant=_timeline_plant(),
        observations=[_timeline_observation(1, "initial")],
        diagnoses=[_timeline_diagnosis(10, 1, "Overwatering", day=1)],
        roadmap_steps=[],
        feedback_due=False,
    )

    at = AppTest.from_function(_render_timeline_script, args=(detail,))
    at.run()

    assert not at.exception
    assert _RECHECK_MARKER not in [c.value for c in at.caption]


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


def _render_feedback_script() -> None:
    import streamlit as st

    from ui.components.feedback import render_feedback_prompt

    calls = st.session_state.setdefault("_feedback_calls", [])

    def on_submit(rating: int | None, did_it_help: str | None, text: str | None) -> None:
        calls.append((rating, did_it_help, text))

    render_feedback_prompt(on_submit=on_submit)


def test_feedback_prompt_renders_a_form():
    at = AppTest.from_function(_render_feedback_script)
    at.run()
    assert not at.exception
    assert at.radio
    assert at.feedback
    assert at.button


def test_submitting_feedback_calls_on_submit():
    at = AppTest.from_function(_render_feedback_script)
    at.run()
    at.radio[0].set_value("yes")
    at.button[0].click().run()

    # No star touched: rating stays None, which the nullable column accepts.
    assert at.session_state["_feedback_calls"] == [(None, "yes", "")]


def test_submitting_feedback_passes_the_star_rating_through():
    """``rating`` used to be hardcoded to ``None``, so the column's
    ``CHECK (rating BETWEEN 1 AND 5)`` constraint could never fire on a real value.
    ``st.feedback`` is 0-based, so the fourth star has to arrive as 4, not 3."""
    at = AppTest.from_function(_render_feedback_script)
    at.run()
    at.feedback[0].set_value(3)
    at.button[0].click().run()

    rating, _, _ = at.session_state["_feedback_calls"][0]
    assert rating == 4


def test_submitting_feedback_passes_a_non_default_option_and_free_text():
    at = AppTest.from_function(_render_feedback_script)
    at.run()
    at.radio[0].set_value("too_early")
    at.feedback[0].set_value(0)
    at.text_area[0].set_value("Only three days in, hard to tell.")
    at.button[0].click().run()

    assert at.session_state["_feedback_calls"] == [
        (1, "too_early", "Only three days in, hard to tell.")
    ]
