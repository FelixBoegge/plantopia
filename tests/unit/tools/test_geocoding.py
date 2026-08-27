"""Naming the place at a coarse position.

**The parsing tests are built from recorded responses, not written ones.** The three files
under `tests/fixtures/nominatim_*.json` are what the live service returned on 2026-08-27 for
a city, a rural county, and a position in the North Sea. A fixture written from documentation
tests the documentation; `U2` is this project's entry on what that is worth.

The third one is the reason recording matters. A position with nothing at it answers **HTTP
200** with `{"error": "Unable to geocode"}` — not a 404, not an empty body. An adapter
trusting the status code would hand that object to its parser, and no amount of imagining
would have produced that fixture.
"""

import json
import pathlib

import httpx
import pytest
import respx

from tools.geocoding import DEFAULT_URL, forget, place_name

FIXTURES = pathlib.Path("tests/fixtures")


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"nominatim_{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _an_empty_cache():
    """The cache is module state, shared by every test in the process.

    Without this, the second test to ask about a position gets the first one's answer and
    makes no request — which is the behaviour under test in one place and a silent
    false pass everywhere else.
    """
    forget()
    yield
    forget()


class TestNamingAPlace:
    @respx.mock
    def test_names_a_city(self):
        respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        assert place_name(52.5, 13.4) == "Berlin"

    @respx.mock
    def test_names_a_county_where_there_is_no_town(self):
        """A rural position has no city, town or village. The recording proves the
        fall-through order is right rather than plausible — this response carries `county`
        and `state` and nothing more specific."""
        respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("rural")))

        assert place_name(51.1, -3.2) == "Somerset"

    @respx.mock
    def test_a_position_with_nothing_at_it(self):
        """200 with an error body, which is what the live service actually does."""
        respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("nowhere")))

        assert place_name(54.5, 3.2) is None

    @respx.mock
    def test_says_in_the_log_that_there_was_nothing_there(self, caplog):
        """The fall-through would return `None` for this body anyway — no address, no
        rendered name — so the explicit check earns its place by what it writes down.
        "Nothing at that position" and "the service is broken" look identical from the
        return value and want different responses from whoever reads the log.
        """
        respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("nowhere")))

        with caplog.at_level("DEBUG", logger="tools.geocoding"):
            place_name(54.5, 3.2)

        assert "Unable to geocode" in caplog.text

    @respx.mock
    def test_falls_back_to_the_first_part_of_a_rendered_address(self):
        """A response with no structured address at all. Its `display_name` starts with the
        most specific thing found, which at this zoom is a place rather than a building."""
        body = recorded("city")
        del body["address"]
        respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=body))

        assert place_name(52.5, 13.4) == "Berlin"


class TestWhatItSends:
    @respx.mock
    def test_identifies_itself(self):
        """A requirement of the service's terms, and the one most often ignored."""
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        place_name(52.5, 13.4)

        assert "Plantopia" in route.calls[0].request.headers["User-Agent"]

    @respx.mock
    def test_asks_at_roughly_city_level(self):
        """Asking for more detail than an eleven-kilometre position carries would invite a
        street name for a position that cannot support one."""
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        place_name(52.5, 13.4)

        assert route.calls[0].request.url.params["zoom"] == "10"

    @respx.mock
    def test_sends_the_position_it_was_given(self):
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        place_name(52.5, 13.4)

        params = route.calls[0].request.url.params
        assert params["lat"] == "52.5"
        assert params["lon"] == "13.4"

    @respx.mock
    def test_can_be_pointed_somewhere_else(self):
        """A deployment doing more than occasional lookups is expected by the terms to run
        its own instance."""
        elsewhere = "https://geocoding.example/reverse"
        route = respx.get(elsewhere).mock(return_value=httpx.Response(200, json=recorded("city")))

        place_name(52.5, 13.4, base_url=elsewhere, user_agent="Somebody/1.0")

        assert route.call_count == 1
        assert route.calls[0].request.headers["User-Agent"] == "Somebody/1.0"


class TestTheCache:
    @respx.mock
    def test_one_position_is_looked_up_once(self):
        """Every photograph from one garden rounds to the same coarse position, so this is
        what keeps ordinary use inside the one-request-a-second the terms ask for."""
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        assert place_name(52.5, 13.4) == "Berlin"
        assert place_name(52.5, 13.4) == "Berlin"

        assert route.call_count == 1

    @respx.mock
    def test_a_different_position_is_looked_up_again(self):
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(200, json=recorded("city")))

        place_name(52.5, 13.4)
        place_name(51.1, -3.2)

        assert route.call_count == 2

    @respx.mock
    def test_a_failure_is_remembered_too(self):
        """A service that is down stays down for a while. Retrying on every upload would be
        a retry storm against a free service."""
        route = respx.get(DEFAULT_URL).mock(return_value=httpx.Response(503))

        assert place_name(52.5, 13.4) is None
        assert place_name(52.5, 13.4) is None

        assert route.call_count == 1


class TestWhenItFails:
    """None of these may raise, and none may cost anybody an upload.

    This is the only external call in the project that happens while somebody is waiting to
    press a button rather than inside a ninety-second run.
    """

    @pytest.mark.parametrize(
        "outcome",
        [
            httpx.Response(400),
            httpx.Response(403),
            httpx.Response(429),
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=["a list, not an object"]),
            httpx.Response(200, json={}),
            httpx.ConnectError("no route to host"),
            httpx.ReadTimeout("took too long"),
        ],
        ids=[
            "bad-request",
            "forbidden",
            "rate-limited",
            "server-error",
            "unavailable",
            "unparseable",
            "wrong-shape",
            "empty-object",
            "connection-refused",
            "timeout",
        ],
    )
    @respx.mock
    def test_returns_nothing_and_raises_nothing(self, outcome):
        if isinstance(outcome, Exception):
            respx.get(DEFAULT_URL).mock(side_effect=outcome)
        else:
            respx.get(DEFAULT_URL).mock(return_value=outcome)

        assert place_name(52.5, 13.4) is None
