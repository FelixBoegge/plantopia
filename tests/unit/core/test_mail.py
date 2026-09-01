"""The email port: what gets used, what gets written, and what happens when it fails.

The property worth protecting is that a machine without a provider configured cannot mail
a real person, so that is asserted directly rather than assumed from the settings default.
"""

import logging

import httpx
import pytest

from core.config import Settings
from core.mail import ConsoleMailer, Message, ResendMailer, build_mailer
from tests.secrets import TEST_JWT_SECRET

MESSAGE = Message(
    to="someone@example.test",
    subject="Confirm your address",
    body="Follow this link: https://example.test/verify?token=abc123",
)


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, **overrides
    )


def test_without_a_provider_the_console_adapter_is_chosen():
    """The safe adapter is the default, not something a developer has to select."""
    assert isinstance(build_mailer(_settings()), ConsoleMailer)


def test_the_test_suites_own_settings_never_produce_a_sending_adapter():
    """Guards the constraint rather than the code path: if a future default were to carry a
    provider key, this fails before any test mails anybody."""
    assert not isinstance(build_mailer(_settings()), ResendMailer)


def test_a_configured_provider_is_used():
    mailer = build_mailer(_settings(resend_api_key="re_test_key"))

    assert isinstance(mailer, ResendMailer)


def test_the_console_adapter_does_not_claim_to_reach_an_inbox():
    """What the registration and reset screens tell somebody rests on this. An adapter that
    only writes to a log must say so, or the screen sends them to an inbox nothing arrives
    in."""
    assert ConsoleMailer().reaches_inbox is False


def test_a_configured_provider_reaches_an_inbox():
    assert (
        ResendMailer(api_key="re_test_key", sender="Plantopia <hello@example.test>").reaches_inbox
        is True
    )


def test_the_console_adapter_writes_the_whole_message_where_it_can_be_read(caplog):
    """Including the link — the developer following it is the point of the adapter."""
    with caplog.at_level(logging.INFO, logger="core.mail"):
        delivered = ConsoleMailer().send(MESSAGE)

    assert delivered
    written = caplog.text
    assert MESSAGE.to in written
    assert MESSAGE.subject in written
    assert "https://example.test/verify?token=abc123" in written


def test_a_provider_failure_is_reported_rather_than_raised(monkeypatch, caplog):
    """A verification message can be requested again; a lost registration cannot be undone,
    so an unreachable provider must not fail the request that triggered the send."""

    def _unreachable(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", _unreachable)
    mailer = ResendMailer(api_key="re_test_key", sender="Plantopia <hello@example.test>")

    with caplog.at_level(logging.ERROR, logger="core.mail"):
        delivered = mailer.send(MESSAGE)

    assert delivered is False
    assert MESSAGE.to in caplog.text


def test_a_failure_is_logged_without_the_link(monkeypatch, caplog):
    """The body carries a working credential, and a log is a less careful place than an
    inbox."""

    def _unreachable(*args, **kwargs):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", _unreachable)
    mailer = ResendMailer(api_key="re_test_key", sender="Plantopia <hello@example.test>")

    with caplog.at_level(logging.ERROR, logger="core.mail"):
        mailer.send(MESSAGE)

    assert "token=abc123" not in caplog.text


def test_a_rejected_send_is_reported_rather_than_raised(monkeypatch):
    """A provider that answers with an error is the same story as one that does not answer:
    the caller carries on."""
    request = httpx.Request("POST", ResendMailer.ENDPOINT)
    response = httpx.Response(422, json={"message": "invalid sender"}, request=request)
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    mailer = ResendMailer(api_key="re_test_key", sender="Plantopia <hello@example.test>")

    assert mailer.send(MESSAGE) is False


def test_a_successful_send_addresses_the_provider_as_documented(monkeypatch):
    """Pins the request shape, because a silently-wrong field name would look exactly like
    a working adapter until somebody checked an inbox."""
    sent = {}

    def _capture(url, **kwargs):
        sent["url"] = url
        sent.update(kwargs)
        return httpx.Response(200, json={"id": "abc"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _capture)
    mailer = ResendMailer(api_key="re_test_key", sender="Plantopia <hello@example.test>")

    assert mailer.send(MESSAGE) is True
    assert sent["url"] == ResendMailer.ENDPOINT
    assert sent["headers"]["Authorization"] == "Bearer re_test_key"
    assert sent["json"] == {
        "from": "Plantopia <hello@example.test>",
        "to": [MESSAGE.to],
        "subject": MESSAGE.subject,
        "text": MESSAGE.body,
    }


def test_a_send_cannot_hang_a_request_open(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: (
            seen.update(kwargs) or httpx.Response(200, request=httpx.Request("POST", url))
        ),
    )

    ResendMailer(api_key="k", sender="s").send(MESSAGE)

    assert seen["timeout"] == pytest.approx(10.0)
