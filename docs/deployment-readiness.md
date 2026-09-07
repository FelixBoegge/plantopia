# Deployment readiness

What has to be true before Plantopia is reachable at a public URL. Written 2026-09-07,
against the tree at that date.

The short version: the application is feature-complete and verified by CI, and **nothing in
this repository produces a runnable artefact**. There is no Dockerfile, and
`docker-compose.yml` brings up only the database. That is `M51`, recorded deliberately on
2026-09-01 — the capstone review came first, and a running instance means a public URL
against paid OpenRouter and Pl@ntNet keys. This document is the list that closes it.

Items are grouped by what happens if you skip them: the first group breaks the deployment,
the second lets it run wrongly, the third is what you would regret in a month.

---

## 1. Blockers — it does not work without these

### 1.1 Build artefacts

- [ ] **Multi-stage `Dockerfile` for the API.** Python 3.12, `uv sync --frozen`, then
      `uvicorn api.main:create_app --factory`. Note that there is deliberately no
      module-level `app` — `api/main.py` says why — so the `--factory` flag is not optional.
- [ ] **Multi-stage `Dockerfile` for the frontend.** `npm ci && npm run build` produces
      `web/dist`; the runtime stage is a static server or a reverse proxy.
- [ ] **`api` and `frontend` services in `docker-compose.yml`.** The compose file's own
      comment already anticipates this ("The API container joins this network later"). Inside
      the network the database is `db:5432`, not `localhost:5433` — the published port exists
      only for host access.

### 1.2 The frontend and the API must be same-origin

This is the constraint most likely to be discovered late, because it is invisible in
development.

`web/src/api/client.ts` sets `const BASE = "/api/v1"` — a **relative** path. There is no
`VITE_API_URL` and no absolute origin anywhere in the client. In development Vite's proxy
(`web/vite.config.ts`) forwards `/api` to `http://localhost:8000`; in production nothing
does that unless you build it.

Reinforcing the same conclusion: the refresh cookie is `SameSite=Strict`
(`api/cookies.py`), and Vite's config comments say so explicitly — a cross-origin frontend
would not receive it at all, so sessions could never be renewed.

- [ ] **Serve both behind one origin.** A reverse proxy (nginx, Caddy, Traefik) that serves
      `web/dist` at `/` and proxies `/api` to the API container. Splitting them across two
      hostnames means rewriting the client's base URL *and* relaxing the cookie to `Lax`,
      which is a security change, not a configuration one.
- [ ] Leave `PLANTOPIA_CORS_ORIGINS` **empty** if you do this. Same-origin needs no CORS,
      and `api/main._add_cors` skips the middleware entirely when nothing is configured —
      the absence of the middleware is the policy.

### 1.3 Database schema and corpus

- [ ] **`alembic upgrade head` on API start**, before the server accepts traffic.
      `data/migrations/env.py:31` reads the URL from `Settings`, so no `sqlalchemy.url` in
      `alembic.ini` needs setting — only `PLANTOPIA_DATABASE_URL`.
- [ ] **`python -m knowledge.ingest_corpus` as a one-shot** after the migration. This
      **makes model calls** — one embedding request per batch for 301 sections, roughly
      $0.0005 — so it needs the OpenRouter key present. It is idempotent by
      `doc_id::section`, so re-running it is safe.
- [ ] **Confirm the corpus landed:** 301 chunks across 43 documents at 1536 dimensions.
      ```
      docker compose exec -T db psql -U plantopia -d plantopia         -c "SELECT count(*), count(DISTINCT doc_id) FROM corpus_chunks;"
      ```
      This is a hard gate, not a sanity check. Since 2026-09-07 `corpus_chunks` is the
      *only* place retrieval reads, so a migrated-but-not-ingested database serves every
      diagnosis with no reference material at all — and says so politely rather than
      failing, which is the worst way for it to be wrong.

### 1.4 A real mail provider

**Without this nobody but you can sign in.** `identity/accounts.authenticate` treats an
unverified account exactly like an unknown address or a wrong password — one refusal for all
three — and registration creates the account unverified. Absent `resend_api_key`,
`core/mail.build_mailer` returns `ConsoleMailer`, which writes the verification link to the
log. That is correct for development and useless for anybody who is not reading your
container logs.

- [ ] Set `PLANTOPIA_RESEND_API_KEY` and `PLANTOPIA_MAIL_FROM` to a verified sender.
      The default, `Plantopia <onboarding@resend.dev>`, is Resend's shared testing sender.
- [ ] Set `PLANTOPIA_APP_URL` to the real public address. **Every link in every email is
      built from it**, so the default `http://localhost:5173` produces verification links
      that nobody can follow and that nothing warns you about.
- [ ] Register once against the deployment and follow the link from a real inbox.

### 1.5 Required secrets with no defaults

The application refuses to construct `Settings` without these two, which is the intended
behaviour — a missing secret should stop the process, not start a broken one.

- [ ] `PLANTOPIA_OPENROUTER_API_KEY` — every model call in the application goes through it.
- [ ] `PLANTOPIA_JWT_SECRET` — at least 32 characters (RFC 7518's floor for HMAC-SHA256).
      **It must be stable across restarts and identical in every process.** A generated one
      works perfectly in development and logs everybody out at random in production. Store
      it in the platform's secret manager, not in an image layer.

### 1.6 Do not run more than one API process

`M28`: rate-limit counters (`api/rate_limit.py`), the run executor's thread pool, and the
event bus (`runs/bus.py`) all live in one process's memory. Two workers behind one address
would permit twice the rate limit, run twice the configured pool, and — the one a user
notices — leave a client connected to process B watching a run on process A, seeing an empty
stream.

- [ ] **One replica, one worker.** No `--workers 2`, no horizontal autoscaling.
- [ ] If you ever need a second process, substitute first: Redis or `LISTEN`/`NOTIFY` for the
      bus, Redis or the proxy for the limiter, a real worker behind `RunExecutor` (which is
      already behind a port for exactly this). Then set
      `PLANTOPIA_RUN_SWEEPER_ENABLED=false` on all but one.

---

## 2. Runs, but wrongly

### 2.1 Re-lock the evaluation page to admins

**Currently open to every signed-in account, on purpose and temporarily** — so the capstone
reviewer can see it with the member account they register. Close it before the deployment is
public: harness results are internal numbers, and the route is `/admin/evaluation` for a
reason.

It is a configuration switch rather than an edit to the rule, specifically so this task
cannot be forgotten into production. `identity/roles.may_read_evaluations` still answers
admin-only by default, `Settings.evaluation_open_to_members` defaults to `False`, and a
deployment that says nothing inherits the closed state. So the re-lock is a deletion, and
the failure mode of forgetting it is a *closed* page rather than an open one.

- [ ] **Delete `PLANTOPIA_EVALUATION_OPEN_TO_MEMBERS=true` from `.env`** — or simply do not
      set it in the deployment's environment, which is the same thing.
- [ ] Promote your own account:
      `UPDATE users SET role='admin' WHERE email='…';`
- [ ] Confirm a member account gets a 404 (not a 403 — a refusal that distinguishes the two
      tells a stranger the route exists), and that your admin account still gets 200.
- [ ] Once the review is over, consider deleting the switch entirely — the setting, its
      parameter on `may_read_evaluations`, and the two tests that pin the opened state. It
      earns its place only while a reviewer needs it.

### 2.2 Trusted proxy headers

`api/rate_limit.source_of` returns `request.client.host`, which behind a proxy is the proxy.
Every visitor then shares one budget of 10 requests per 300 seconds on the three
unauthenticated auth endpoints — so the first few visitors lock out the rest. `M28` calls
this the part that "matters sooner".

- [ ] Configure `--proxy-headers` and `--forwarded-allow-ips` on uvicorn, and make the proxy
      set `X-Forwarded-For` — or move rate limiting into the proxy and leave the in-process
      limiter as a backstop.

### 2.3 Cookies over HTTPS

- [ ] Terminate TLS. Leave `PLANTOPIA_SECURE_COOKIES=true` (the default); `False` is
      defensible only for plain-http localhost, and over HTTPS the refresh cookie is dropped
      without it.

### 2.4 Cost controls

A diagnosis costs roughly $0.022–$0.026 measured (`docs/known-limitations.md`, the species
second-opinion entries). Open self-registration without limits is an unmetered bill with a
signup form — the defaults exist for that reason, but they were chosen for one developer.

- [ ] Review `PLANTOPIA_MONTHLY_RUN_ALLOWANCE` (default 20 per account per calendar month).
- [ ] Review `PLANTOPIA_DAILY_SPEND_CAP_USD` (default 5.0, global across all accounts).
      At ~$0.024 a diagnosis that is roughly 200 diagnoses a day before everything stops.
- [ ] Set a hard spend limit on the OpenRouter key itself. The application's cap is enforced
      from its own `usage_events` ledger; a bug there is a bug in your only brake.
- [ ] Decide what `PLANTOPIA_TIER_ALLOWANCES` should hold, if anything. A tier absent from it
      gets the default, deliberately.

### 2.5 Settings whose defaults are development choices

| Setting | Default | Why it needs a decision |
|---|---|---|
| `PLANTOPIA_APP_URL` | `http://localhost:5173` | Every email link (see 1.4) |
| `PLANTOPIA_DATABASE_URL` | `…@localhost:5433/plantopia` | Host-published dev port; inside compose it is `db:5432` |
| `PLANTOPIA_CORS_ORIGINS` | empty | Keep empty if same-origin (1.2) |
| `PLANTOPIA_LOG_LEVEL` | `INFO` | `INFO` logs the console mailer's full message bodies |
| `PLANTOPIA_CONSENT_VERSION` | `2026-08-25` | Stored per account; bump only when the notice actually changes |
| `PLANTOPIA_GEOCODING_USER_AGENT` | a github.com placeholder | Nominatim's terms require a real contact address, and its shared service allows one request a second |

### 2.6 Optional keys that degrade silently

Both are absent-by-default and the application is designed to run without them — but the
capability just does not happen, and nothing on the page says so.

- [ ] `PLANTOPIA_PLANTNET_API_KEY` — without it the species second opinion does not happen
      and the diagnosis proceeds on the vision model's guess alone.
- [ ] `PLANTOPIA_TAVILY_API_KEY` — without it the chat agent's web search is unavailable.

---

## 3. Operational, and worth having before you need it

- [ ] **Database backups.** One Postgres holds the domain tables, the corpus vectors and both
      LangGraph checkpointers. `pgdata` is a compose volume; a `docker compose down -v`
      destroys every account.
- [ ] **LangSmith project separation.** As of 2026-09-07 the application itself traces, not
      just the evaluation harness — so this now decides where real user traffic is recorded.
      `PLANTOPIA_LANGSMITH_PROJECT` points at a sprint-scoped project; give production its
      own, so demo traffic and real traffic are not read as one. The key is region-scoped: an
      EU-workspace key needs `PLANTOPIA_LANGSMITH_ENDPOINT` set, or it 403s against the
      default US host and tracing uploads nowhere while reporting itself enabled.
- [ ] **Decide whether to trace at all.** Traces carry prompts, and prompts carry what an
      owner wrote about their plant and where it lives. Omitting the key is the whole
      opt-out; nothing else changes.
- [ ] **Health check.** `api/routers/health.py` is already mounted under the prefix — point
      the platform's probe at it.
- [ ] **Log retention and access.** At `INFO`, and with `ConsoleMailer` in play for any
      environment without a mail key, logs contain password-reset and verification links.
- [ ] **A staging pass.** Register, verify, diagnose, chat, export, delete an account — the
      whole path, on the real deployment, once.
- [ ] **No volume for a vector store.** Retrieval moved to pgvector on 2026-09-07, so
      `data/chroma` and `PLANTOPIA_CHROMA_PATH` no longer exist. The corpus is rows in the
      same Postgres as everything else, which means it is covered by the backup above and
      needs no mount of its own — but also that a restored database is only useful if
      `corpus_chunks` came with it.

---

## 4. Accepted, not blocking

Recorded here so nobody rediscovers them as surprises during a deployment review. Each is
argued in full in `docs/known-limitations.md`.

- **`U18`** — an access token outlives the account it belongs to, for up to fifteen minutes.
- **`U19`** — an export names the corpus passages a diagnosis cited but does not include
  their text.
- **`U23`** — the diagnosis screen shows neither the consulted passages, the tool-call
  detail, nor the recorded `cost_usd`. Open work, not a deployment blocker.
- **`M31`** — keep-alive emission on an event stream is not covered by a test.
- **Diagnostic accuracy** is 89.3% top-1 / 96.4% top-3 on a 28-case golden set
  (2026-08-19 baseline). The harness costs about $1.55 a run and is never run by CI.

---

## Pre-flight

Run in order, and stop at the first failure:

```bash
uv run ruff check . && uv run ruff format --check .
docker compose up -d db && uv run pytest          # ~2½ minutes, gate at 85%
cd web && npm run build && npm test && npx playwright test
```

Then, against the deployed instance: register from a real inbox, follow the verification
link, run one diagnosis end to end, and confirm `usage_events` charged it.
