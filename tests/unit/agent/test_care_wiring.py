"""The care-profile port, as the real wirings actually build it.

`tests/unit/agent/test_port_arity.py` checks that every wired lambda takes the number of
arguments `Deps` declares. It cannot see this change: `care_profile` keeps its arity and
alters its *return*, gaining an origin and sources that two surfaces now read.

That is the same shape of hole the last port change fell through — every node test passed
because every node test supplied its own fake, and only a browser run found it. So these
tests drive the real `build_deps` rather than a double, and assert on a *researched* profile
rather than the curated one that would pass whatever the tiers behind it did.
"""

import ast
import pathlib

import pytest

import agent.wiring as wiring
from agent.schemas import CareOrigin, CareProfile, Passage
from core.config import Settings
from core.ids import new_id
from data.repositories.care_profiles import CareProfileRepository
from tests.secrets import TEST_JWT_SECRET

RUN_EVAL = pathlib.Path("eval/run_eval.py")


@pytest.fixture
def settings() -> Settings:
    return Settings(openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, _env_file=None)


@pytest.fixture
def offline(monkeypatch):
    """Everything `build_deps` would otherwise reach the network for.

    Patched on the module rather than passed in, because these names are read at call time
    inside `build_deps` — which is exactly how `tests/e2e/server.py` keeps a browser run
    off the network, and the reason this can test the real function rather than a copy of it.
    """
    monkeypatch.setattr(wiring, "_shared_retriever", lambda _settings: None)
    monkeypatch.setattr(wiring, "build_gate_model", lambda: _Model())
    monkeypatch.setattr(wiring, "build_vision_model", lambda: None)
    monkeypatch.setattr(wiring, "build_reasoning_model", lambda: None)
    monkeypatch.setattr(
        wiring,
        "web_search_plant_info",
        lambda query, **_kwargs: [
            Passage(
                doc_id="web:example.test",
                section="Calathea orbifolia care",
                text="Bright indirect light. Keep evenly moist. 18-24C. High humidity.",
                score=0.9,
            )
        ],
    )


class _Model:
    """Reports that the material describes exactly the species that was asked about."""

    def with_structured_output(self, schema, **_kwargs):
        return _Runnable(schema)


class _Runnable:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, prompt, *_args, **_kwargs):
        asked = str(prompt).split("Species asked about:", 1)[1].split("\n", 1)[0].strip()
        return self.schema(
            describes_species=asked,
            light="Bright indirect light",
            water="Keep evenly moist",
            temperature_min_c=18,
            temperature_max_c=24,
            humidity="Above 60 percent",
        )


class TestTheApplicationWiring:
    def _deps(self, db, settings):
        return wiring.build_deps(
            user_id=new_id(), profile_facts=lambda: "", settings=settings, session=db
        )

    def test_a_curated_species_is_curated(self, db, settings, offline):
        profile = self._deps(db, settings).care_profile("monstera")

        assert profile is not None
        assert profile.origin is CareOrigin.CURATED

    def test_an_unknown_species_comes_back_researched(self, db, settings, offline):
        """The assertion the arity test cannot make. A wiring left on the old shape returns
        a profile with no origin at all, or none — and every node test would still pass."""
        profile = self._deps(db, settings).care_profile("Calathea orbifolia")

        assert profile is not None
        assert profile.origin is CareOrigin.RESEARCHED
        assert profile.sources == ["web:example.test"]

    def test_the_researched_profile_is_recorded(self, db, settings, offline):
        """Written on its own session, so this reads it back through a different one."""
        self._deps(db, settings).care_profile("Calathea orbifolia")

        assert CareProfileRepository(db).get("Calathea orbifolia") is not None

    def test_the_second_lookup_does_not_search_again(self, db, settings, offline, monkeypatch):
        deps = self._deps(db, settings)
        deps.care_profile("Calathea orbifolia")

        searched = []
        monkeypatch.setattr(
            wiring,
            "web_search_plant_info",
            lambda query, **_kw: searched.append(query) or [],
        )
        again = self._deps(db, settings).care_profile("Calathea orbifolia")

        assert again is not None
        assert again.origin is CareOrigin.RESEARCHED
        assert searched == []


class TestTheHarnessWiring:
    """The evaluation harness builds `Deps` by hand and is excluded from coverage, so
    nothing executes its lambdas until somebody spends money on a run.

    It is wired to the curated tier *only*, deliberately — the same reasoning that leaves
    `identify_species` and `place_name` stubbed there. Research is a network call inside a
    measurement, and reading the shared cache would make a score depend on which species
    other runs happened to have researched first.

    Read from the source rather than by importing `run_eval`, which would open a database
    and build a reasoning model.
    """

    def _care_argument(self) -> ast.expr:
        tree = ast.parse(RUN_EVAL.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Deps"
        ]
        assert len(calls) == 1
        for keyword in calls[0].keywords:
            if keyword.arg == "care_profile":
                return keyword.value
        raise AssertionError("run_eval does not supply care_profile")

    def test_it_builds_the_lookup_rather_than_passing_the_bare_function(self):
        """The bare `lookup_plant_care_profile` still exists and is still correct, so a
        harness left pointing at it would pass every test and quietly measure the old shape."""
        call = self._care_argument()

        assert isinstance(call, ast.Call)
        assert call.func.id == "make_care_profile_lookup"

    def test_it_wires_neither_tier(self):
        call = self._care_argument()

        assert [keyword.arg for keyword in call.keywords] == []

    def test_the_curated_tier_still_answers(self):
        """Whatever the harness does about the tiers, a golden case whose species the
        curated set covers must still get its baseline."""
        from tools.care_profiles import make_care_profile_lookup

        lookup = make_care_profile_lookup()

        assert lookup("Monstera deliciosa") is not None
        assert lookup("Calathea orbifolia") is None


class TestTheGoldenSetTriggersNothing:
    def test_no_golden_species_can_reach_research(self):
        """By construction rather than by coincidence: the harness wires no research tier,
        so no golden case can call one however its species is spelled.

        Worth stating plainly, because 21 of the 28 golden species have no curated baseline
        and would be researched in production. The evaluation therefore cannot measure what
        this change does — recorded as a limitation rather than hidden behind a green test.
        """
        call = TestTheHarnessWiring()._care_argument()

        assert not any(keyword.arg == "research" for keyword in call.keywords)


class TestTheStoredProfileIsNotACareProfileShapedHole:
    def test_a_curated_species_never_reads_the_cache(self, db, settings, offline):
        """A stored row for a curated species must never be reachable — the trusted tier is
        a Python dict and always wins."""
        repo = CareProfileRepository(db)
        repo.put(
            CareProfile(
                species="Monstera deliciosa",
                light="Wrong",
                water="Wrong",
                temperature_c=(0, 1),
                humidity="Wrong",
                origin=CareOrigin.RESEARCHED,
                sources=["web:wrong.test"],
            ),
            now=__import__("datetime").datetime(2026, 8, 31, tzinfo=__import__("datetime").UTC),
        )
        db.flush()

        profile = wiring.build_deps(
            user_id=new_id(), profile_facts=lambda: "", settings=settings, session=db
        ).care_profile("Monstera deliciosa")

        assert profile is not None
        assert profile.origin is CareOrigin.CURATED
        assert profile.light != "Wrong"
