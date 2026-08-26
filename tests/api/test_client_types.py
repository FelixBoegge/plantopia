"""The web client's hand-written types match what the API sends.

Hand-written rather than generated, deliberately: there are a dozen shapes, and a generator
is a build step and a dependency for the saving of an afternoon. What it is not is a licence
to guess — the first version of `Candidate` here invented four field names, and the way that
would have been discovered is a blank card in a browser.

So the claim is checked. This reads the TypeScript and compares its fields against the
OpenAPI schema the application actually publishes.
"""

import pathlib
import re

import pytest

from api.main import create_app
from core.config import Settings
from tests.secrets import TEST_JWT_SECRET

TYPES = pathlib.Path("web/src/api/types.ts")

# Which TypeScript interface corresponds to which schema the API publishes. Only the shapes
# the client actually reads: a schema nobody consumes has nothing to disagree with.
PAIRS = {
    "Plant": "PlantOut",
    "PlantSummary": "PlantSummaryOut",
    "Observation": "ObservationOut",
    "PlantDetail": "PlantDetailOut",
    "Candidate": "CandidateOut",
    "Diagnosis": "DiagnosisOut",
    "RoadmapStep": "RoadmapStepOut",
    "DiagnosisDetail": "DiagnosisDetailOut",
    "Message": "MessageOut",
    "ProfileFact": "ProfileFactOut",
    "Run": "RunOut",
    "Account": "AccountOut",
    "Session": "SessionOut",
    "Evaluation": "EvaluationOut",
}


def _schemas() -> dict:
    app = create_app(
        Settings(
            _env_file=None,
            openrouter_api_key="k",
            jwt_secret=TEST_JWT_SECRET,
            run_sweeper_enabled=False,
        )
    )
    return app.openapi()["components"]["schemas"]


def _fields_of(interface: str) -> set[str]:
    """The property names one TypeScript interface declares."""
    source = TYPES.read_text(encoding="utf-8")
    body = re.search(rf"export interface {interface} \{{(.*?)\n\}}", source, re.DOTALL)
    assert body is not None, f"the client declares no interface named {interface}"
    return set(re.findall(r"^\s*(\w+)[?]?:", body.group(1), re.MULTILINE))


@pytest.mark.parametrize(("interface", "schema"), sorted(PAIRS.items()))
def test_the_client_expects_only_fields_the_api_sends(interface, schema):
    """A field the client reads and the API does not send is `undefined` on a screen."""
    published = set(_schemas()[schema]["properties"])
    expected = _fields_of(interface)

    assert expected <= published, (
        f"{interface} expects fields {sorted(expected - published)} that {schema} does not send"
    )


@pytest.mark.parametrize(("interface", "schema"), sorted(PAIRS.items()))
def test_the_client_knows_about_every_field_the_api_sends(interface, schema):
    """The other direction, and the softer one: a field the API sends and the client ignores
    is a feature nobody can see. Failing here is a prompt to decide, not necessarily a bug.
    """
    published = set(_schemas()[schema]["properties"])
    expected = _fields_of(interface)

    assert published <= expected, (
        f"{schema} sends fields {sorted(published - expected)} that {interface} ignores"
    )
