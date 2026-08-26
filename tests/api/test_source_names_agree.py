"""The client and the server call each lookup the same thing.

A reply's chips are drawn from the transcript by the client; the progress shown while that
reply was being produced comes from the server's own events. Two tables, one vocabulary —
and if they drift, the same lookup is announced one way while it happens and another way
afterwards, on the same screen.

Kept as two tables rather than one because they are in different languages and neither can
import the other. What is not acceptable is that nobody notices when they disagree.
"""

import pathlib
import re

from services.chat_events import TOOL_NAMES

CLIENT = pathlib.Path("web/src/screens/chat/sources.ts")


def _client_names() -> dict[str, str]:
    source = CLIENT.read_text(encoding="utf-8")
    block = re.search(r"const NAMES: Record<string, string> = \{(.*?)\n\};", source, re.DOTALL)
    assert block is not None, "the client's source-name table could not be found"
    return dict(re.findall(r'\s*(\w+):\s*"([^"]+)"', block.group(1)))


def test_both_sides_name_the_same_tools():
    assert set(_client_names()) == set(TOOL_NAMES)


def test_both_sides_use_the_same_words():
    """Otherwise "consulting the disorder reference" becomes "consulted the corpus" the
    moment the reply lands."""
    assert _client_names() == TOOL_NAMES


def test_neither_side_names_a_tool_by_its_identifier():
    for tool, described in {**TOOL_NAMES, **_client_names()}.items():
        assert tool not in described, f"{tool} is announced by its own name"
        assert "_" not in described, f"{described} reads like an identifier"
