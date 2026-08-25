"""The refresh cookie: where it lives, and why it is set the way it is.

One module because these attributes are a security decision, not a call-site detail, and
because setting and clearing must agree on every one of them — a cookie cleared with a
different path is a cookie that is still there.
"""

from fastapi import Response

from core.config import Settings

NAME = "plantopia_refresh"


def path_for(settings: Settings) -> str:
    """The only paths the cookie is sent to.

    Scoped to the auth routes because nothing else reads it. A refresh token attached to
    every request is a refresh token in every log, every proxy and every error report.
    """
    return f"{settings.api_prefix}/auth"


def attach(response: Response, token: str, *, settings: Settings) -> None:
    """Set the refresh cookie.

    ``httponly`` so a script that manages to run on the page cannot read it — which is the
    entire reason the refresh token is a cookie and the access token is not.

    ``samesite="strict"`` so another site cannot make the browser spend it. Strict rather
    than lax: nothing here is a navigation somebody arrives at from elsewhere, so the
    usability cost that usually argues for lax does not apply.
    """
    response.set_cookie(
        NAME,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=path_for(settings),
        max_age=settings.refresh_token_days * 24 * 60 * 60,
    )


def clear(response: Response, *, settings: Settings) -> None:
    """Remove it. Same name and path, or the browser keeps the one that is there."""
    response.delete_cookie(
        NAME,
        path=path_for(settings),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
    )
