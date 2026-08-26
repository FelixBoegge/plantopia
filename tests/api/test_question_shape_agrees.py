"""The client's `Question` matches the one the graph actually sends.

Clarifying questions reach a client in a **stream event**, not in a response body. Nothing
in FastAPI describes that payload, so it is absent from the OpenAPI document and
`test_client_types.py` — which compares the client's interfaces against that document —
cannot see it. This is the one shape on the wire with no schema behind it.

It duly went wrong. The client declared `prompt` where `agent.schemas.Question` declares
`text`, and omitted `kind` altogether, so every question rendered as an unlabelled text box:
including the drainage question, whose four fixed options the graph reasons over. Every
component test passed, because the fixtures had been written from the client's interface
rather than from the graph's.

Neither side can import the other. What is not acceptable is that nobody notices when they
disagree.
"""

import pathlib
import re

from agent.schemas import Question

CLIENT = pathlib.Path("web/src/api/types.ts")


def _interface() -> str:
    """The body of the client's `Question` interface.

    Scoped to the interface rather than searched across the whole file: `location_kind` also
    ends in `kind:`, and matching that instead compares a plant's location to a question's
    kind, then fails for a reason that has nothing to do with either.
    """
    source = CLIENT.read_text(encoding="utf-8")
    block = re.search(r"export interface Question \{(.*?)\n\}", source, re.DOTALL)
    assert block is not None, "the client's Question interface could not be found"
    return block.group(1)


def test_the_client_declares_every_field_a_question_carries():
    declared = set(re.findall(r"^\s*(\w+)\??:", _interface(), re.MULTILINE))
    assert declared == set(Question.model_fields)


def test_the_client_offers_every_kind_a_question_can_be():
    """A kind the client does not handle is a control it renders as something else."""
    declared = re.search(r'kind:\s*((?:"[a-z]+"\s*\|?\s*)+);', _interface())
    assert declared is not None, "the client's question kinds could not be found"

    kinds = set(re.findall(r'"([a-z]+)"', declared.group(1)))
    annotation = Question.model_fields["kind"].annotation
    assert kinds == set(getattr(annotation, "__args__", ()))
