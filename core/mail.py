"""Sending email, and the two ways it happens.

A port with two adapters, because the two differ in a way that matters: one delivers to a
real inbox and one does not. Development and the test suite must never reach the first.
Which is used is decided by whether a provider is configured, not by a flag somebody has to
remember to set — the safe adapter is what you get by default.

**A failed send does not fail the caller.** Every message this system sends is a
verification or reset link, and every one of them can be requested again. Losing a
registration because a third party was briefly unreachable trades a recoverable problem for
an unrecoverable one, so adapters log and return.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from core.config import Settings

logger = logging.getLogger(__name__)

# Long enough to survive an ordinary hiccup, short enough that a hanging provider does not
# hold a registration request open.
SEND_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class Message:
    """One email. Plain text only: everything sent here is a sentence and a link."""

    to: str
    subject: str
    body: str


class Mailer(Protocol):
    """Somewhere to send a message."""

    reaches_inbox: bool
    """Whether a message sent here can arrive in somebody's inbox.

    Not the same question as whether a send succeeded. This one is about the adapter, is
    the same for every message, and is what lets a screen say where a link actually went
    instead of telling everybody to check their email. It says nothing about any particular
    address, which is what keeps it safe to return from an endpoint that must not reveal
    whether an address is registered.
    """

    def send(self, message: Message) -> bool:
        """Send it. Returns whether it was delivered.

        Never raises for a delivery failure. The return value exists for logging and for
        tests, not to make callers branch — a caller that refused to continue on ``False``
        would be reintroducing the coupling this port removes.
        """
        ...


class ConsoleMailer:
    """Writes the message to the log instead of sending it.

    The default, and what runs in development and in tests. It prints the whole body,
    including the link, because the developer clicking that link is the point.
    """

    reaches_inbox = False

    def send(self, message: Message) -> bool:
        logger.info(
            "email not sent (no provider configured); to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.body,
        )
        return True


class ResendMailer:
    """Sends through Resend's HTTP API."""

    ENDPOINT = "https://api.resend.com/emails"
    reaches_inbox = True

    def __init__(self, *, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    def send(self, message: Message) -> bool:
        try:
            response = httpx.post(
                self.ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._sender,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.body,
                },
                timeout=SEND_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            # Logged without the body: it carries a working verification or reset link, and
            # a log is a less careful place than an inbox.
            logger.exception("could not send email to %s (subject=%s)", message.to, message.subject)
            return False
        return True


def build_mailer(settings: Settings) -> Mailer:
    """The adapter this configuration implies.

    No provider configured means the console, which is why a machine that has never been
    given a Resend key cannot accidentally mail a real person.
    """
    if not settings.resend_api_key:
        return ConsoleMailer()
    return ResendMailer(api_key=settings.resend_api_key, sender=settings.mail_from)
