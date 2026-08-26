"""The Pl@ntNet adapter, and the fact that nothing it does can stop a diagnosis.

Most of this file is about failure. That is the proportion the risk deserves: the happy path
is one parse, and every other case is a third party the diagnosis must survive. The parsing
tests here use a hand-written body only as far as task 2.3 — from there they are built from a
response actually recorded from the service, because a fixture written from an assumption
tests the assumption.
"""

import httpx
import pytest
import respx

from agent.schemas import ImageOrgan, SpeciesMethod
from tools.plantnet import IDENTIFY_URL, MAX_IMAGES, WIRE_ORGANS, identify_species

KEY = "plantnet-test-key"


def _photo(organ: ImageOrgan = ImageOrgan.LEAF, body: bytes = b"jpeg-bytes"):
    return (body, organ)


def _result(name: str, score: float, scientific: str = "Ocimum basilicum"):
    return {
        "score": score,
        "species": {
            "scientificName": f"{scientific} L.",
            "scientificNameWithoutAuthor": scientific,
            "commonNames": [name],
        },
    }


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
    @respx.mock
    def test_returns_candidates_ranked_as_the_service_ranked_them(self):
        respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        _result("Basil", 0.82),
                        _result("Thai basil", 0.11, "Ocimum × africanum"),
                    ]
                },
            )
        )

        found = identify_species([_photo()], api_key=KEY)

        assert [c.common_name for c in found] == ["Basil", "Thai basil"]
        assert found[0].confidence == pytest.approx(0.82)

    @respx.mock
    def test_every_candidate_says_where_it_came_from(self):
        respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": [_result("Basil", 0.82)]})
        )

        found = identify_species([_photo()], api_key=KEY)

        assert found[0].method is SpeciesMethod.PLANTNET

    @respx.mock
    def test_keeps_the_scientific_name_alongside_the_common_one(self):
        """ "Basil" is what somebody calls their plant; the scientific name is what makes two
        spellings of it comparable. Keeping one and discarding the other loses a use."""
        respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(200, json={"results": [_result("Basil", 0.82)]})
        )

        found = identify_species([_photo()], api_key=KEY)

        assert found[0].common_name == "Basil"
        assert found[0].scientific_name == "Ocimum basilicum"

    @respx.mock
    def test_falls_back_to_the_scientific_name_when_there_is_no_common_one(self):
        """Most of 50,000 species have no common name in any language."""
        body = _result("unused", 0.4)
        body["species"]["commonNames"] = []
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json={"results": [body]}))

        found = identify_species([_photo()], api_key=KEY)

        assert found[0].common_name == "Ocimum basilicum"

    @respx.mock
    def test_skips_a_result_that_is_missing_what_it_needs(self):
        """A partial answer from a second opinion is still a second opinion."""
        respx.post(IDENTIFY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"score": 0.9, "species": {}},  # no name at all
                        _result("Basil", 0.82),
                    ]
                },
            )
        )

        found = identify_species([_photo()], api_key=KEY)

        assert [c.common_name for c in found] == ["Basil"]

    @respx.mock
    def test_an_empty_result_set_is_not_a_failure(self):
        respx.post(IDENTIFY_URL).mock(return_value=httpx.Response(200, json={"results": []}))

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
