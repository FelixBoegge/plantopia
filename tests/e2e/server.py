"""The API, wired to scripted models, for the browser tests to drive.

Run as its own process:

    uv run python -m tests.e2e.server

**The patch lives here rather than behind a setting.** A `PLANTOPIA_SCRIPTED_MODELS` flag
would be a switch that silently disables the model, shipped in the same package as the
thing it disables — one environment variable away from a deployment that answers every
diagnosis from a canned differential and looks entirely healthy while doing it. Replacing
the three builders from a module under `tests/` cannot reach production, because nothing
production imports can import it.

The database is its own — created, migrated and dropped by this module — so a browser run
can never touch development data, and so 'against a clean database' means it.
"""

import os
import sys
from pathlib import Path
from shutil import rmtree

from sqlalchemy import text
from sqlalchemy.engine import make_url

# Patched before anything imports the wiring that calls them. `agent.wiring` binds these
# names at import time, so patching only the defining module would arrive after the binding
# and do nothing — which is why each one is replaced in both places.
import core.llm  # noqa: E402
from tests.e2e.models import ScriptedGraphModel  # noqa: E402
from tests.fakes.embeddings import HashingEmbeddings  # noqa: E402

core.llm.build_reasoning_model = lambda **_: ScriptedGraphModel()
core.llm.build_vision_model = lambda **_: ScriptedGraphModel()
core.llm.build_gate_model = lambda **_: ScriptedGraphModel()

import agent.wiring  # noqa: E402

agent.wiring.build_reasoning_model = core.llm.build_reasoning_model
agent.wiring.build_vision_model = core.llm.build_vision_model
agent.wiring.build_gate_model = core.llm.build_gate_model

# Embedding the corpus is a model call too. The rule is about the network, not about which
# tier of model is on the other end of it — and this one is easy to overlook precisely
# because nothing in the graph looks like it is asking for an embedding. Hashing embeddings
# give the corpus a real vector space with real word overlap, so the chat agent's lookup
# returns genuine passages rather than a stub.
agent.wiring.build_embeddings = lambda: HashingEmbeddings()

# Mail goes to a file the browser tests read, so a test can click the link a person would
# have been sent rather than reaching past it into the database.
import core.mail  # noqa: E402

from tests.e2e.mail import FileMailer, forget as forget_mail  # noqa: E402

core.mail.build_mailer = lambda _settings: FileMailer()

import api.dependencies  # noqa: E402

api.dependencies.build_mailer = core.mail.build_mailer

from core.config import Settings  # noqa: E402
from data.engine import build_engine  # noqa: E402

DATABASE = "plantopia_e2e"
PORT = 8100


def settings() -> Settings:
    """Configuration for a browser run: this module's database, and a known secret.

    `_env_file=None` for the same reason every test-side construction passes it — a key in
    a developer's own .env changing the behaviour of a test run is a failure that reproduces
    on one machine and nowhere else (M6).
    """
    configured = make_url(
        Settings(
            _env_file=None,
            openrouter_api_key="sk-e2e-not-used",
            jwt_secret="e2e-jwt-secret-long-enough-to-be-accepted-by-the-settings",
        ).database_url
    )
    return Settings(
        _env_file=None,
        openrouter_api_key="sk-e2e-not-used",
        jwt_secret="e2e-jwt-secret-long-enough-to-be-accepted-by-the-settings",
        database_url=configured.set(database=DATABASE).render_as_string(hide_password=False),
        app_url="http://localhost:5173",
        # Its own Chroma directory, and not the development one: a browser run embeds the
        # corpus with hashing embeddings, and those vectors must never end up in a
        # collection a real run then searches.
        chroma_path=Path(__file__).resolve().parent / ".chroma",
    )


def exports() -> Settings:
    """Put this run's configuration in the environment, and return it.

    Everything downstream — the app's own `get_settings`, the checkpointer, and Alembic's
    `env.py` — reads the environment rather than taking an argument, so the environment is
    where a browser run's configuration has to be before any of them runs.
    """
    configured = settings()
    os.environ["PLANTOPIA_DATABASE_URL"] = configured.database_url
    os.environ["PLANTOPIA_JWT_SECRET"] = configured.jwt_secret
    os.environ["PLANTOPIA_OPENROUTER_API_KEY"] = configured.openrouter_api_key
    os.environ["PLANTOPIA_APP_URL"] = configured.app_url
    # The run worker builds its own `Settings` from the environment rather than being handed
    # the app's, so anything omitted here silently falls back to the development default.
    # Omitting this one opened the *development* Chroma collection and tried to upsert
    # 256-dimension hashing vectors into a 1536-dimension space — which fails, loudly, and
    # only after a run has already been started.
    os.environ["PLANTOPIA_CHROMA_PATH"] = str(configured.chroma_path)
    return configured


def recreate() -> str:
    """Drop and rebuild the browser-test database. Returns its URL."""
    configured = make_url(settings().database_url)
    maintenance = configured.set(database="postgres").render_as_string(hide_password=False)

    admin = build_engine(maintenance)
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{DATABASE}"'))
    finally:
        admin.dispose()

    url = configured.render_as_string(hide_password=False)
    engine = build_engine(url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()
    return url


def migrate() -> None:
    """Bring the browser-test database to head.

    Alembic rather than ``create_all``: a browser run is the closest thing here to a
    deployment, and running the migrations is the part of a deployment most worth having
    exercised by something other than its own test.

    **Reads the URL from the environment, which `exports` must have set first.**
    `data/migrations/env.py` deliberately ignores alembic.ini's `sqlalchemy.url` and
    constructs `Settings()` instead, so setting it on the `Config` here does nothing at all:
    the first version of this function did exactly that and migrated the *development*
    database while reporting success. It was a no-op only because that database was already
    at head.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")


def _forget_chroma(path: Path) -> None:
    """Delete the browser run's vector store, for the same reason the database is dropped.

    A collection left by an earlier run was embedded by an earlier corpus. Reusing it makes
    a retrieval test pass or fail on something no longer in the repository.
    """
    if path.exists():
        rmtree(path)


def main() -> int:
    import uvicorn

    from api.main import create_app

    configured = exports()
    forget_mail()
    _forget_chroma(configured.chroma_path)
    recreate()
    migrate()

    uvicorn.run(create_app(configured), host="127.0.0.1", port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
