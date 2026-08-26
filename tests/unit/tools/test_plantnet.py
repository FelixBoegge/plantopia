"""The Pl@ntNet adapter, and the fact that nothing it does can stop a diagnosis.

Most of this file is about failure. That is the proportion the risk deserves: the happy path
is one parse, and every other case is a third party the diagnosis must survive.

**The parsing tests are built from a recorded response, not a written one.**
`tests/fixtures/plantnet_identify.json` is what the live service returned on 2026-08-26 for
two photographs from `test_pics/`. A fixture written from documentation tests the
documentation, and `U2` is this project's entry about what that is worth. Where an edge case
needs a shape the recording does not contain, the recording is *mutated*, so even those start
from something real.

The recorded plant is a Rhaphidophora, which the service ranks above two Monsteras. That the
top three are three plausible near-relatives rather than one confident answer is itself worth
having in a fixture: it is what a real identification looks like.
"""

import json
import pathlib

import httpx
import pytest
import respx

from agent.schemas import ImageOrgan, SpeciesMethod
from tools.plantnet import IDENTIFY_URL, MAX_IMAGES, WIRE_ORGANS, identify_species

KEY = "plantnet-test-key"

FIXTURE = pathlib.Path("tests/fixtures/plantnet_identify.json")


def _recorded() -> dict:
    """The real response, read fresh so one test's mutation cannot reach another."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _photo(organ: ImageOrgan = ImageOrgan.LEAF, body: bytes = b"jpeg-bytes"):
    return (body, organ)


class TestWithoutAKey:
    def test_no_key_makes_no_request_at_all(self):
        """Not a failed request: none. A machine that has never been given a key must not
        be able to reach the service by accident, and `respx` asserting on an empty route
        list is the only way to say that."""
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(IDENTIFY_URL)

            assert identify_species([_photo()], api_key=None) == []
            assert route.call_count == 0

    def test_an_empty_key_is_treated_as_no_key(self):
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(IDENTIFY_URL)

            assert identify_species([_photo()], api_key="") == []
            assert route.call_count == 0

    def test_no_photographs_makes_no_request(self):
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(IDENTIFY_URL)

            assert identify_species([], api_key=KEY) == []
            assert route.call_count == 0


class TestWhenItAnswers:
    """Every assertion here is against what the service actually returned."""

    @respx.mock
    def test_returns_candidates_in_the_order_the_service_ranked_them(self):
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=_recorded()))

        found = identify_species([_photo()], api_key=KEY)

        assert [c.common_name for c in found] == [
            "Mini monstera",
            "Monstera",
            "Mini monstera",
        ]
        assert found[0].confidence == pytest.approx(0.6311, abs=1e-4)
        assert [c.confidence for c in found] == sorted((c.confidence for c in found), reverse=True)

    @respx.mock
    def test_every_candidate_says_where_it_came_from(self):
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=_recorded()))

        found = identify_species([_photo()], api_key=KEY)

        assert {c.method for c in found} == {SpeciesMethod.PLANTNET}

    @respx.mock
    def test_keeps_the_scientific_name_alongside_the_common_one(self):
        """The recording makes the case better than an invented body could: its first and
        third candidates share the common name "Mini monstera" and are different plants.
        Discarding the scientific name would leave two identical-looking choices."""
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=_recorded()))

        found = identify_species([_photo()], api_key=KEY)

        assert found[0].common_name == found[2].common_name
        assert found[0].scientific_name == "Rhaphidophora tetrasperma"
        assert found[2].scientific_name == "Monstera minima"

    @respx.mock
    def test_takes_the_scientific_name_without_its_author(self):
        """The recording carries both. `Rhaphidophora tetrasperma Hook.f.` names a botanist,
        which is not something to put in front of somebody asking about their houseplant."""
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=_recorded()))

        found = identify_species([_photo()], api_key=KEY)

        assert "Hook.f." not in (found[0].scientific_name or "")

    @respx.mock
    def test_falls_back_to_the_scientific_name_when_there_is_no_common_one(self):
        """Most of 50,000 species have no common name in any language."""
        body = _recorded()
        body["results"][0]["species"]["commonNames"] = []
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=body))

        found = identify_species([_photo()], api_key=KEY)

        assert found[0].common_name == "Rhaphidophora tetrasperma"

    @respx.mock
    def test_skips_a_result_that_is_missing_what_it_needs(self):
        """A partial answer from a second opinion is still a second opinion."""
        body = _recorded()
        body["results"][0]["species"] = {}  # no name at all
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=body))

        found = identify_species([_photo()], api_key=KEY)

        assert [c.common_name for c in found] == ["Monstera", "Mini monstera"]

    @respx.mock
    def test_returns_no_more_candidates_than_it_was_asked_for(self):
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=_recorded()))

        found = identify_species([_photo()], api_key=KEY, max_results=2)

        assert len(found) == 2

    @respx.mock
    def test_an_empty_result_set_is_not_a_failure(self):
        body = _recorded()
        body["results"] = []
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json=body))

        assert identify_species([_photo()], api_key=KEY) == []


class TestWhatItSends:
    @respx.mock
    def test_sends_the_key_and_the_photographs(self):
        route = respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        identify_species([_photo(), _photo(ImageOrgan.FLOWER)], api_key=KEY)

        request = route.calls[0].request
        assert f"api-key={KEY}" in str(request.url)
        assert request.content.count(b"jpeg-bytes") == 2

    @respx.mock
    def test_names_each_photographs_organ(self):
        route = respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        identify_species([_photo(ImageOrgan.BARK), _photo(ImageOrgan.FLOWER)], api_key=KEY)

        body = route.calls[0].request.content
        assert b"bark" in body
        assert b"flower" in body

    @respx.mock
    def test_sends_no_organ_for_a_photograph_whose_organ_is_unknown(self):
        """Guessing a hint for a specialist classifier is worse than giving it none."""
        route = respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        identify_species([_photo(ImageOrgan.UNKNOWN)], api_key=KEY)

        assert b"unknown" not in route.calls[0].request.content

    @respx.mock
    def test_can_omit_organs_entirely(self):
        """The escape hatch for the unverified vocabulary: a request that names no organ
        cannot be rejected for naming one the service does not know."""
        route = respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        identify_species([_photo(ImageOrgan.LEAF)], api_key=KEY, omit_organs=True)

        body = route.calls[0].request.content
        assert b"organs" not in body
        assert b"jpeg-bytes" in body

    @respx.mock
    def test_sends_no_more_photographs_than_the_service_accepts(self):
        """A diagnosis with seven photographs must send some rather than fail."""
        route = respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": []})
        )

        identify_species([_photo() for _ in range(7)], api_key=KEY)

        assert route.calls[0].request.content.count(b"jpeg-bytes") == MAX_IMAGES


class TestWhenItFails:
    """Every one of these proceeds with nothing rather than raising.

    Table-driven because the point is the completeness of the list, not any one entry: a
    failure mode missing from here is a failure mode that reaches the graph.
    """

    @pytest.mark.parametrize(
        "outcome",
        [
            httpx.Response(400),
            httpx.Response(401),
            httpx.Response(404),
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, text="not json at all"),
            httpx.Response(200, json=["a list, not an object"]),
            httpx.Response(200, json={"results": "not a list"}),
            httpx.ConnectError("no route to host"),
            httpx.ReadTimeout("took too long"),
        ],
        ids=[
            "bad-request",
            "unauthorised",
            "not-found",
            "server-error",
            "unavailable",
            "unparseable-body",
            "wrong-shape",
            "wrong-results-type",
            "connection-refused",
            "timeout",
        ],
    )
    @respx.mock
    def test_returns_nothing_and_raises_nothing(self, outcome):
        if isinstance(outcome, Exception):
            respx.post(IDENTIFY_URL).mock(side_effect=outcome)
        else:
            respx.post(IDENTIFY_URL).mock(return_value=outcome)

        assert identify_species([_photo()], api_key=KEY) == []

    @respx.mock
    def test_an_exhausted_allowance_is_logged_as_itself(self, caplog):
        """ "You have run out until tomorrow" and "something broke" want different responses
        from whoever reads the log, and the same response from the diagnosis."""
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(429, json={}))

        with caplog.at_level("WARNING"):
            assert identify_species([_photo()], api_key=KEY) == []

        assert "allowance" in caplog.text.lower()


def test_the_wire_vocabulary_covers_every_organ_that_is_sent():
    """`UNKNOWN` is ours and is never sent; everything else must have a wire value.

    Adding a member to the enum without adding it here would silently stop sending that
    organ — the classifier would go on working, slightly worse, with nothing to notice.
    """
    sent = set(ImageOrgan) - {ImageOrgan.UNKNOWN}

    assert set(WIRE_ORGANS) == sent


class TestARefusedRequest:
    """A 400 is the one failure worth a second attempt.

    Confirmed against the live service: an organ outside its vocabulary fails the whole
    request rather than being ignored. Left alone, one wrong value in `WIRE_ORGANS` would
    disable identification for every diagnosis, silently and for ever, while every test in
    this file went on passing.
    """

    @respx.mock
    def test_retries_once_without_organs(self):
        route = respx.post(IDENTIFY_URL).mock(
            side_effect=[
                httpx.Response(400, json={"message": "unknown organ"}),
                httpx.Response(200, json=_recorded()),
            ]
        )

        found = identify_species([_photo(ImageOrgan.HABIT)], api_key=KEY)

        assert route.call_count == 2
        assert b"habit" in route.calls[0].request.content
        assert b"organs" not in route.calls[1].request.content
        assert found[0].common_name == "Mini monstera"

    @respx.mock
    def test_does_not_retry_a_request_that_already_had_no_organs(self):
        """Otherwise a genuinely malformed request is sent twice for nothing."""
        route = respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(400, json={}))

        assert identify_species([_photo()], api_key=KEY, omit_organs=True) == []
        assert route.call_count == 1

    @respx.mock
    def test_gives_up_when_the_retry_also_fails(self):
        route = respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(400, json={}))

        assert identify_species([_photo(ImageOrgan.LEAF)], api_key=KEY) == []
        assert route.call_count == 2

    @respx.mock
    def test_says_in_the_log_what_to_look_at(self, caplog):
        """A warning that names `WIRE_ORGANS` is the difference between a five-minute fix
        and an afternoon: the retry means the symptom is a slightly worse answer, not a
        broken one, so nothing else will point at the cause."""
        respx.post(IDENTIFY_URL).mock(
            side_effect=[
                httpx.Response(400, json={}),
                httpx.Response(200, json=_recorded()),
            ]
        )

        with caplog.at_level("WARNING"):
            identify_species([_photo(ImageOrgan.LEAF)], api_key=KEY)

        assert "WIRE_ORGANS" in caplog.text
