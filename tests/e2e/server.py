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

Imports below are deliberately out of order and interleaved with assignments: each patch has
to be in place before the module that reads the patched name is imported. That is the whole
mechanism, so E402 is disabled for the file rather than silenced line by line.
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

# Patched before anything imports the wiring that calls them. `agent.wiring` binds these
# names at import time, so patching only the defining module would arrive after the binding
# and do nothing — which is why each one is replaced in both places.
import core.llm
from tests.e2e.models import ScriptedGraphModel, scripted_second_opinion, scripted_weather
from tests.fakes.embeddings import HashingEmbeddings

core.llm.build_reasoning_model = lambda **_: ScriptedGraphModel()
core.llm.build_vision_model = lambda **_: ScriptedGraphModel()
core.llm.build_gate_model = lambda **_: ScriptedGraphModel()

import agent.wiring

agent.wiring.build_reasoning_model = core.llm.build_reasoning_model
agent.wiring.build_vision_model = core.llm.build_vision_model
agent.wiring.build_gate_model = core.llm.build_gate_model

# Embedding the corpus is a model call too. The rule is about the network, not about which
# tier of model is on the other end of it — and this one is easy to overlook precisely
# because nothing in the graph looks like it is asking for an embedding. Hashing embeddings
# give the corpus a real vector space with real word overlap, so the chat agent's lookup
# returns genuine passages rather than a stub.
agent.wiring.build_embeddings = lambda: HashingEmbeddings()

# The second identification, scripted rather than absent. Clearing the key (see `exports`)
# would also work and would offer no choice at all — and the choice between two methods that
# disagree is the part of this worth driving a browser through.
agent.wiring.plantnet_identify = lambda photographs, **_: scripted_second_opinion(photographs)

# Reverse geocoding, scripted. The photographs under `test_pics/` carry no position since
# their GPS was stripped, so nothing would call this today — which is exactly why it is
# patched: a fixture that gains a position later would otherwise reach a live, rate-limited
# service from a test suite that promises to make no network calls, and nothing would say
# so.
agent.wiring.reverse_geocode = lambda latitude, longitude, **_: "Testville"

# Weather, scripted. This one was reaching Open-Meteo for real on every outdoor run — the
# only outbound call in this file's list that was not patched, and it went unnoticed because
# an outdoor browser test passes whether the weather is real or not. Scripted it is also
# *deterministic*: a test that asserts on a frost date cannot do so against whatever the
# weather actually did.
agent.wiring.get_local_weather = scripted_weather

# Mail goes to a file the browser tests read, so a test can click the link a person would
# have been sent rather than reaching past it into the database.
import core.mail
from tests.e2e.mail import FileMailer
from tests.e2e.mail import forget as forget_mail

core.mail.build_mailer = lambda _settings: FileMailer()

import api.dependencies

api.dependencies.build_mailer = core.mail.build_mailer

from core.config import Settings
from data.engine import build_engine

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
        # Every browser test registers, verifies and signs in, and all of them arrive from
        # one address — so the default of ten attempts per five minutes is spent about three
        # tests in, and everything after it fails for a reason that has nothing to do with
        # what it was testing. The limit itself is exercised in
        # `tests/api/test_rate_limits.py`, against the real default.
        auth_rate_limit=10_000,
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
    # `PLANTOPIA_DATABASE_URL` above is what now keeps the corpus separate: the vectors live
    # in this run's own database, so there is no longer a store on disk to point elsewhere.
    os.environ["PLANTOPIA_AUTH_RATE_LIMIT"] = str(configured.auth_rate_limit)

    # **Every third-party credential blanked, by name.**
    #
    # `settings()` above passes `_env_file=None`, but the worker does not: it builds its
    # own `Settings` from the environment, which reads `.env`. So a developer's real
    # Pl@ntNet or Tavily key reaches the graph and a browser run makes real calls to real
    # services — spending someone's daily allowance, and quietly making a test suite that
    # promises to make no network calls into one that does. It depends on what is in a file
    # that is not in the repository, which means it would work on CI and not on the machine
    # of whoever added the key.
    #
    # Cleared rather than overwritten with a fake: an empty key is the configured-absent
    # path each adapter already handles, and the browser tests script the second opinion in
    # `Deps` anyway.
    for credential in ("PLANTOPIA_PLANTNET_API_KEY", "PLANTOPIA_TAVILY_API_KEY"):
        os.environ[credential] = ""

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


def _seed_corpus(configured: Settings) -> None:
    """Embed the corpus into this run's database, offline.

    Retrieval reads `corpus_chunks`, and `recreate()` leaves it empty — so without this a
    browser diagnosis retrieves nothing and the run reports having found no reference
    material. This replaces deleting a Chroma directory: the vectors are rows in this
    run's own database now, dropped with it rather than left on disk.

    `HashingEmbeddings` for the same reason the models are scripted — a browser run must
    not call a provider. Its vectors are the corpus column's width, so they store as they
    are.
    """
    from agent.wiring import open_session
    from data.models import CorpusChunk
    from knowledge.ingest import chunk_text, load_corpus
    from tests.fakes.embeddings import HashingEmbeddings

    chunks = load_corpus(configured.corpus_path)
    texts = [chunk_text(chunk) for chunk in chunks]
    vectors = HashingEmbeddings().embed_documents(texts)

    session = open_session(configured)
    try:
        session.add_all(
            [
                CorpusChunk(
                    doc_id=chunk.doc_id,
                    section=chunk.section,
                    name=chunk.name,
                    content=text,
                    category=chunk.category,
                    transmissible=chunk.transmissible,
                    severity=chunk.severity,
                    embedding=vector,
                )
                for chunk, text, vector in zip(chunks, texts, vectors, strict=True)
            ]
        )
        session.commit()
    finally:
        session.close()


def main() -> int:
    import uvicorn

    from api.main import create_app

    configured = exports()
    forget_mail()
    recreate()
    migrate()
    # After migrate: the table has to exist before rows can go into it.
    _seed_corpus(configured)

    uvicorn.run(create_app(configured), host="127.0.0.1", port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
