"""What the emails say.

Kept apart from the logic that sends them so that changing a sentence is not changing a
security boundary, and so a test can assert what a person receives without going through a
provider.

Plain text, and short. Every one of these is a sentence and a link.
"""

from urllib.parse import quote

from core.mail import Message

VERIFY_PATH = "/verify"
RESET_PATH = "/reset"


def _link(base_url: str, path: str, token: str) -> str:
    """The link, with the token escaped.

    Escaped because it is URL-safe base64 and the alphabet is *nearly* safe — the padding
    and separator characters that appear in other token schemes are exactly what would
    silently truncate a link.
    """
    return f"{base_url.rstrip('/')}{path}?token={quote(token, safe='')}"


def verification(*, base_url: str, token: str, hours: int) -> tuple[str, str]:
    """Subject and body for proving an address."""
    return (
        "Confirm your Plantopia address",
        "Welcome to Plantopia.\n\n"
        "Confirm this address to finish setting up your account:\n\n"
        f"{_link(base_url, VERIFY_PATH, token)}\n\n"
        f"The link works for the next {hours} hours. "
        "If you did not create an account, you can ignore this message.\n",
    )


def already_registered(*, base_url: str) -> tuple[str, str]:
    """Sent when somebody registers an address that already has an account.

    The registration response cannot say the account exists — that would answer "who has an
    account here?" to anybody who asks. The address itself can be told, because whoever
    holds it already knows.
    """
    return (
        "Someone tried to register your Plantopia address",
        "Somebody just tried to create a Plantopia account with this address, "
        "which already has one.\n\n"
        "If that was you, sign in instead — or reset your password if you have "
        f"forgotten it:\n\n{base_url.rstrip('/')}{RESET_PATH}\n\n"
        "If it was not you, no action is needed. No account was created and "
        "nothing has changed.\n",
    )


def password_reset(*, base_url: str, token: str, hours: int) -> tuple[str, str]:
    """Subject and body for choosing a new password."""
    return (
        "Reset your Plantopia password",
        "Use this link to choose a new password:\n\n"
        f"{_link(base_url, RESET_PATH, token)}\n\n"
        f"The link works for the next {hours} hours and only once. "
        "Using it signs you out everywhere.\n\n"
        "If you did not ask for this, you can ignore this message — "
        "your password has not changed.\n",
    )


def compose(to: str, subject_and_body: tuple[str, str]) -> Message:
    """Address one of the above to somebody."""
    subject, body = subject_and_body
    return Message(to=to, subject=subject, body=body)
