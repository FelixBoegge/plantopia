"""The claim in ``services/limits`` that nothing calls it, kept honest.

A note saying "not wired yet" is worth exactly as much as whatever checks it. When the run
endpoints arrive and call ``check``, this test fails — which is the reminder to delete both
the note and the test rather than leaving a docstring that has quietly become false.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]

# Where application code lives. Tests are excluded on purpose: they call the guard directly,
# which is what testing it means.
APPLICATION = ("api", "agent", "services", "data", "core", "eval", "knowledge", "tools")


def _sources():
    for package in APPLICATION:
        yield from (ROOT / package).rglob("*.py")


def test_nothing_in_the_application_calls_the_guard():
    callers = [
        path.relative_to(ROOT).as_posix()
        for path in _sources()
        if path.name != "limits.py" and "limits.check(" in path.read_text(encoding="utf-8")
    ]

    assert callers == [], (
        f"{callers} now call the quota guard — remove the 'nothing calls check yet' note "
        "in services/limits.py, and delete this test"
    )


def test_the_note_saying_so_is_still_there():
    """The other half: if somebody deletes the note without wiring anything, the module
    stops explaining why a complete, tested guard is unreached.
    """
    source = (ROOT / "services" / "limits.py").read_text(encoding="utf-8")

    assert "Nothing calls ``check`` yet" in source
