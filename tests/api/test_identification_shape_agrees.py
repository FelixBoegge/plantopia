"""The client's `SpeciesCandidate` matches the one the graph sends.

The second shape on the wire with no schema behind it. Identification candidates reach a
client in the same stream event as the clarifying questions, so FastAPI describes neither and
`test_client_types.py` — which compares the client's interfaces against the OpenAPI document
— can see neither.

The first one went wrong: `Question` declared `prompt` where the graph declares `text` and
omitted `kind` entirely, so every question rendered as an unlabelled text box. What made it
survive was that the component fixtures had been written from the client's interface rather
than from the graph's, so the tests agreed with the bug. This file is the same check for the
candidates, written before rather than after.
"""

import pathlib
import re

from agent.schemas import SpeciesCandidate, SpeciesMethod

CLIENT = pathlib.Path("web/src/api/types.ts")


def _interface() -> str:
    """The body of the client's `SpeciesCandidate` interface."""
    source = CLIENT.read_text(encoding="utf-8")
    block = re.search(r"export interface SpeciesCandidate \{(.*?)\n\}", source, re.DOTALL)
    assert block is not None, "the client's SpeciesCandidate interface could not be found"
    return block.group(1)


def test_the_client_declares_every_field_a_candidate_carries():
    declared = set(re.findall(r"^\s*(\w+)\??:", _interface(), re.MULTILINE))
    assert declared == set(SpeciesCandidate.model_fields)


def test_the_client_knows_every_method_that_can_produce_one():
    """A method the client does not know is a candidate it cannot attribute — and the
    provenance is the entire reason the choice is worth showing."""
    declared = re.search(r'method:\s*((?:"[a-z_]+"\s*\|?\s*)+);', _interface())
    assert declared is not None, "the client's method union could not be found"

    known = set(re.findall(r'"([a-z_]+)"', declared.group(1)))
    assert known == {method.value for method in SpeciesMethod}
