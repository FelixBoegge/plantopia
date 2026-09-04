"""The links in emails point at pages that exist.

Every verification and reset message once pointed at `localhost:8501/verify` — the port
a retired UI served on, months after that UI was retired, and a path the web client has
never served. Nobody could have completed a registration through the interface, and a link
in an email is unfixable once sent. Nobody can be told the address was wrong.

So the paths are checked against the client's own routing table rather than trusted.
"""

import pathlib
import re

from identity import messages

ROUTES = pathlib.Path("web/src/routes/routes.tsx")


def _declared_routes() -> set[str]:
    """Every path the web client declares a route for."""
    source = ROUTES.read_text(encoding="utf-8")
    return set(re.findall(r'path="([^"]+)"', source))


def test_the_verification_link_points_at_a_route_the_client_serves():
    assert messages.VERIFY_PATH in _declared_routes()


def test_the_reset_link_points_at_a_route_the_client_serves():
    assert messages.RESET_PATH in _declared_routes()


def test_a_verification_link_carries_the_token_as_a_query_parameter():
    """Which is where the screen reads it from."""
    _, body = messages.verification(base_url="https://plantopia.example", token="abc123", hours=24)

    assert "https://plantopia.example/verify-email?token=abc123" in body


def test_a_reset_link_carries_the_token_the_same_way():
    _, body = messages.password_reset(base_url="https://plantopia.example", token="abc123", hours=1)

    assert "https://plantopia.example/reset-password?token=abc123" in body


def test_the_already_registered_notice_points_somewhere_real():
    """It offers a reset to somebody who already has an account, and that offer has to be
    followable."""
    _, body = messages.already_registered(base_url="https://plantopia.example")

    assert "https://plantopia.example/reset-password" in body


def test_the_default_address_is_not_a_service_that_was_retired():
    """The old default outlived the UI it pointed at by two changes, which is exactly how
    long the links were broken."""
    from core.config import Settings
    from tests.secrets import TEST_JWT_SECRET

    settings = Settings(_env_file=None, openrouter_api_key="k", jwt_secret=TEST_JWT_SECRET)

    assert "8501" not in settings.app_url
