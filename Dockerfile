# syntax=docker/dockerfile:1

# Builder: resolve the locked dependency set with uv. Kept separate from the runtime
# stage so the final image carries only the venv it produces, not uv itself or the
# build cache.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependencies first so this layer only rebuilds when pyproject.toml/uv.lock change,
# not on every source edit. --no-dev skips pytest/ruff/ragas/etc — dev-only tooling
# with no place in a deployed image. --no-install-project defers the app's own code
# (copied below) so it isn't invalidated by the same edits.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# core/agent/api/identity/tools/data/knowledge/services/runs are the packages the
# app actually imports at runtime; eval/ is the offline evaluation CLI and tests/
# the test suite — neither ships.
COPY core ./core
COPY agent ./agent
COPY api ./api
COPY identity ./identity
COPY tools ./tools
COPY data ./data
COPY knowledge ./knowledge
COPY services ./services
COPY runs ./runs
COPY alembic.ini ./alembic.ini

# Runtime: same base, no uv, no build cache — just the venv and the application code.
FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 1000 app
COPY --from=builder --chown=app:app /app /app

USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Cloud Run injects $PORT (defaults to 8080 elsewhere); shell form so it expands.
#
# --proxy-headers --forwarded-allow-ips='*' so api/rate_limit.py's source_of() sees the real
# visitor IP from X-Forwarded-For instead of Cloud Run's own internal edge address — every
# request reaching this container has already passed through Cloud Run's front end, which is
# the only thing '*' trusts here. Does not (and cannot, from this container alone) stop a
# caller hitting the API's own public URL directly from forging that header; that gap is
# accepted for now and recorded in docs/deployment-readiness.md §2.2.
CMD exec uvicorn api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} \
    --proxy-headers --forwarded-allow-ips='*'
