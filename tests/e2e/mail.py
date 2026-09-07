"""A mail sink the browser tests can read.

Verification and reset both work by sending somebody a link, so a browser test that skipped
the link would skip the half of the flow most likely to be wrong — this project has already
shipped a verification link pointing at a retired UI's port, and a verification screen
that spent its own token before the person clicked it.

Messages are appended as JSON lines to a file the test reads. Deliberately a file rather
than an endpoint: an endpoint that hands out verification links is a thing that could exist
in a deployment, and this cannot, because nothing outside `tests/` imports it.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from core.mail import Message

SINK = Path(__file__).resolve().parent / "mail.jsonl"


@dataclass
class FileMailer:
    """Writes every message to `SINK` instead of sending it."""

    path: Path = SINK
    # The browser tests exercise the flow a deployment with a provider has, so this stands
    # in for one. The fallback copy has its own tests; sending these down that path would
    # cost the coverage of the ordinary one.
    reaches_inbox: bool = True

    def send(self, message: Message) -> bool:
        with self.path.open("a", encoding="utf8") as handle:
            handle.write(
                json.dumps({"to": message.to, "subject": message.subject, "body": message.body})
                + "\n"
            )
        return True


def forget() -> None:
    """Empty the sink, so one run cannot read another run's link."""
    SINK.unlink(missing_ok=True)
