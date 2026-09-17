# Deployment readiness

What has to be true before Plantopia is reachable at a public URL. Written 2026-09-07,
against the tree at that date. Updated 2026-09-14: the API `Dockerfile` landed and the
database moved off the local container. Updated 2026-09-15: the API and the frontend are
deployed and live, real mail delivery via Resend is configured, and the app is reachable at
its own custom domain, `https://plantopia-ai.com` — noted in place below rather than
rewritten around, so this still reads as the record it was.

The short version: the application is feature-complete and verified by CI, and it is now
publicly reachable end to end at `https://plantopia-ai.com`. `M51`'s three gaps are closed:
the API `Dockerfile` builds and runs, the database is a managed Supabase Postgres, and both
services are deployed to Cloud Run — API in `europe-west3` at
`https://plantopia-api-412420541766.europe-west3.run.app` (`min-instances=0,
max-instances=1`, service account `plantopia-api-run@plantopia-508709.iam.gserviceaccount.com`,
secrets in Secret Manager under the `plantopia-*` names), frontend in `europe-west1`, mapped
to `plantopia-ai.com` (its Cloud Run URL,
`https://plantopia-web-412420541766.europe-west1.run.app`, still works too —
`PLANTOPIA_APP_URL` points at the custom domain). The frontend moved from `europe-west3` (its
original region) to `europe-west1` specifically to support Cloud Run's native domain mapping,
which `europe-west3` doesn't offer — see §3's "Custom domain" item for the full record. The
frontend service is a Caddy
container (`web/Dockerfile`, `web/Caddyfile`) that serves the built static files and
reverse-proxies `/api/**` to the API service — chosen over Firebase Hosting specifically
because Firebase's rewrite-to-Cloud-Run buffers the whole response and cannot carry the SSE
streams `runs/bus.py` depends on for chat and diagnosis. `PLANTOPIA_CORS_ORIGINS` stays empty
— the browser only ever talks to one origin. Mail is configured and live: `ResendMailer` is
active with a verified sender (`mail.plantopia-ai.com`), not the shared/restricted default —
see §1.4. This document is the
list that closes what remains.

Items are grouped by what happens if you skip them: the first group breaks the deployment,
the second lets it run wrongly, the third is what you would regret in a month.

---

## 1. Blockers — it does not work without these

### 1.1 Build artefacts

- [x] **Multi-stage `Dockerfile` for the API.** Python 3.12, `uv sync --frozen`, then
      `uvicorn api.main:create_app --factory`. Note that there is deliberately no
      module-level `app` — `api/main.py` says why — so the `--factory` flag is not optional.
      Landed 2026-09-14, ahead of the rest of this section — it builds and runs, but nothing
      has pushed the image anywhere yet.
- [x] **Multi-stage `Dockerfile` for the frontend.** `npm ci && npm run build` produces
      `web/dist`; the runtime stage is a static server or a reverse proxy. Landed
      2026-09-15 as `web/Dockerfile`: builds with `node:22-slim`, serves with `caddy:2-alpine`
      (`web/Caddyfile`). Deployed to Cloud Run as `plantopia-web`, not composed locally — the
      item below is still open for that.
- [ ] **`api` and `frontend` services in `docker-compose.yml`.** The compose file's own
      comment already anticipates this ("The API container joins this network later"). Inside
      the network the database is `db:5432`, not `localhost:5433` — the published port exists
      only for host access. Note that this is no longer the production database either way
      (see 1.3) — this item is about composing a local all-in-one stack, not about deployment.

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

- [x] **Serve both behind one origin.** A reverse proxy (nginx, Caddy, Traefik) that serves
      `web/dist` at `/` and proxies `/api` to the API container. Splitting them across two
      hostnames means rewriting the client's base URL *and* relaxing the cookie to `Lax`,
      which is a security change, not a configuration one. Done 2026-09-15 via `web/Caddyfile`
      — `reverse_proxy {$API_ORIGIN}` with `flush_interval -1` so SSE isn't buffered. Firebase
      Hosting was considered and rejected for this specific reason: its Cloud Run rewrite
      buffers the whole response.
- [x] Leave `PLANTOPIA_CORS_ORIGINS` **empty** if you do this. Same-origin needs no CORS,
      and `api/main._add_cors` skips the middleware entirely when nothing is configured —
      the absence of the middleware is the policy. Confirmed empty on the live deployment.

### 1.3 Database schema and corpus

**Done, for the database this deployment will use.** `PLANTOPIA_DATABASE_URL` points at a
Supabase Postgres project as of 2026-09-14, and every table — schema, domain rows, both
LangGraph checkpointers, and `corpus_chunks` with its 1536-dim vectors — was migrated there
from the local compose database and verified: row counts match exactly, `blobs` matches by
combined MD5, `corpus_chunks` matches by an order-independent hash of every embedding, and
`alembic_version` is at the same head revision (`139fad2ecae2`) on both sides. There is no
separate corpus to ingest for this database; it travelled with the rest of the migration.

The steps below are the general procedure for provisioning a schema and corpus from
scratch — a different environment, or this one if Supabase is ever replaced. They are not
outstanding work for the current database.

- [x] **`alembic upgrade head` on API start**, before the server accepts traffic.
      `data/migrations/env.py:31` reads the URL from `Settings`, so no `sqlalchemy.url` in
      `alembic.ini` needs setting — only `PLANTOPIA_DATABASE_URL`. True for whichever
      database that variable names; done for Supabase via the migration, not by running
      this on a live API start.
- [ ] **`python -m knowledge.ingest_corpus` as a one-shot**, only if standing up a database
      that does not already have `corpus_chunks` populated. This **makes model calls** — one
      embedding request per batch for 301 sections, roughly $0.0005 — so it needs the
      OpenRouter key present. It is idempotent by `doc_id::section`, so re-running it is safe.
- [ ] **Confirm the corpus landed:** 301 chunks across 43 documents at 1536 dimensions.
      Against the local dev database:
      ```
      docker compose exec -T db psql -U plantopia -d plantopia -c "SELECT count(*), count(DISTINCT doc_id) FROM corpus_chunks;"
      ```
      Against Supabase, the same query via the CLI rather than `docker compose exec` —
      there is no local container to exec into:
      ```
      npx supabase db query --linked "SELECT count(*), count(DISTINCT doc_id) FROM corpus_chunks;"
      ```
      This is a hard gate, not a sanity check. Since 2026-09-07 `corpus_chunks` is the
      *only* place retrieval reads, so a migrated-but-not-ingested database serves every
      diagnosis with no reference material at all — and says so politely rather than
      failing, which is the worst way for it to be wrong.

### 1.4 A real mail provider

**Done as of 2026-09-15.** `identity/accounts.authenticate` treats an unverified account
exactly like an unknown address or a wrong password — one refusal for all three — and
registration creates the account unverified, so without a real mailer nobody but the person
reading container logs could ever sign in. `PLANTOPIA_RESEND_API_KEY` is now set (Secret
Manager, `plantopia-resend-api-key`), so `core/mail.build_mailer` returns `ResendMailer`
rather than `ConsoleMailer` in production.

- [x] Set `PLANTOPIA_RESEND_API_KEY` and `PLANTOPIA_MAIL_FROM` to a verified sender. Not the
      shared `onboarding@resend.dev` testing sender (which only delivers to the address on
      the Resend account itself) — `plantopia-ai.com` was registered specifically for this,
      with a dedicated sending subdomain (`mail.plantopia-ai.com`) verified in Resend via
      DKIM/SPF/MX records added in Cloudflare. `PLANTOPIA_MAIL_FROM` is
      `Plantopia <noreply@mail.plantopia-ai.com>`. This reaches *any* registrant, not just
      one address — open public sign-up works. There is still no SMTP adapter in
      `core/mail.py` (only `ResendMailer` and `ConsoleMailer`) — moot now that Resend is
      configured with a verified domain; an SMTP adapter was considered earlier and dropped
      in favour of this.
- [x] Set `PLANTOPIA_APP_URL` to the real public address. **Every link in every email is
      built from it**, so the default `http://localhost:5173` produces verification links
      that nobody can follow and that nothing warns you about. History, all 2026-09-15: set
      to the API's own URL first, then to the frontend's `europe-west3` URL once that service
      existed, then to its `europe-west1` URL once the frontend moved there, then to
      `https://plantopia-ai.com` once that domain's certificate finished provisioning (§3's
      "Custom domain"). **Current value:** `https://plantopia-ai.com`.
- [x] Register once against the deployment and follow the link from a real inbox. Confirmed
      2026-09-15 by the user against `https://plantopia-ai.com`: registered, the verification
      email arrived from `Plantopia <noreply@mail.plantopia-ai.com>`, the link worked, and the
      account could log in. End to end, for real.

### 1.5 Required secrets with no defaults

The application refuses to construct `Settings` without these two, which is the intended
behaviour — a missing secret should stop the process, not start a broken one.

- [x] `PLANTOPIA_OPENROUTER_API_KEY` — every model call in the application goes through it.
      In Secret Manager as `plantopia-openrouter-api-key` since 2026-09-15. **Temporary
      value, expires in a few days from 2026-09-15** — it is a provided/college-issued key,
      not the user's own. A personal OpenRouter key is coming and must replace it before
      expiry, or every model call (diagnosis, chat, embeddings) starts failing with no
      frontend-visible warning ahead of time. Rotate with:
      ```
      grep -m1 "^PLANTOPIA_OPENROUTER_API_KEY=" .env | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' | tr -d '\n' \
        | gcloud secrets versions add plantopia-openrouter-api-key --data-file=- --project=plantopia-508709
      ```
      then redeploy (`gcloud run deploy` with the same image and no other flags — Cloud Run
      keeps the rest of the service config unless a flag overrides it) so the new revision
      resolves `:latest` again. Also
      re-probe the model slugs in `core/config.py` (`gate_model`, `vision_model`,
      `reasoning_model`) once on a personal key — the current defaults were chosen
      specifically because they work on a *restricted* college-issued key, and a personal
      key may support the stronger models documented as commented-out overrides there.
- [x] `PLANTOPIA_JWT_SECRET` — at least 32 characters (RFC 7518's floor for HMAC-SHA256).
      **It must be stable across restarts and identical in every process.** A generated one
      works perfectly in development and logs everybody out at random in production. Store
      it in the platform's secret manager, not in an image layer. In Secret Manager as
      `plantopia-jwt-secret` since 2026-09-15. **Gotcha hit during setup:** a
      `grep | cut | sed | gcloud secrets create` pipeline (and `openssl rand -base64 ... |
      gcloud secrets create`) leaves a trailing newline in the stored secret — pipe through
      `tr -d '\n'` before `--data-file=-`, or every value silently carries an extra byte
      (broke the database connection outright; would have broken the `Authorization` header
      for API keys too).

### 1.6 Do not run more than one API process

`M28`: rate-limit counters (`api/rate_limit.py`), the run executor's thread pool, and the
event bus (`runs/bus.py`) all live in one process's memory. Two workers behind one address
would permit twice the rate limit, run twice the configured pool, and — the one a user
notices — leave a client connected to process B watching a run on process A, seeing an empty
stream.

- [x] **One replica, one worker.** No `--workers 2`, no horizontal autoscaling. Enforced via
      Cloud Run `--min-instances=0 --max-instances=1` since 2026-09-15.
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

- [x] Configure `--proxy-headers` and `--forwarded-allow-ips` on uvicorn, and make the proxy
      set `X-Forwarded-For` — or move rate limiting into the proxy and leave the in-process
      limiter as a backstop. Done 2026-09-15: `Dockerfile`'s `CMD` adds
      `--proxy-headers --forwarded-allow-ips='*'`, which fixes attribution for the normal
      path (browser → `plantopia-web` Caddy proxy → `plantopia-api`).

      **Not fully closed — accepted gap.** The API also keeps its own public Cloud Run URL
      (`--allow-unauthenticated`). Google's own docs hedge ("generally") on whether Cloud
      Run's default ingress sanitizes a client-supplied `X-Forwarded-For` before adding the
      real one, so a caller hitting that URL directly could plausibly forge the header and
      dodge the auth-endpoint rate limit. Closing it needs either IAM-gating the API
      (`--no-allow-unauthenticated` + `roles/run.invoker` for the frontend's service account,
      with the frontend attaching a signed identity token — Caddy has no built-in way to do
      this, it would need a custom build/plugin or a different proxy) or a network-level
      `--ingress=internal` restriction (which itself needs Direct VPC egress from the
      frontend — a VPC/connector to stand up). Both are real, separate infrastructure work.
      Accepted as low-risk for now: traffic is near zero, and the endpoints this protects
      (register/login/reset) are cheap regardless — the expensive ones (diagnosis/chat) are
      bounded by the daily spend cap (§2.4) independent of IP. Revisit before real traffic.

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
- [ ] Decide what `PLANTOPIA_TIER_ALLOWANCES` should hold, if anything. A tier absent from it
      gets the default, deliberately.
- [ ] **OpenRouter's own guardrails, on the key itself — due whenever the temporary
      college-issued key (§1.5) is replaced with a personal one.** Everything above is
      enforced by this application's own code, reading its own ledger; a bug in that code, or
      a code path that spends without recording, has no backstop unless OpenRouter refuses on
      its own side too. These are account/key settings, not code, at
      `openrouter.ai/settings/keys` and `openrouter.ai/settings/privacy`:
      - [ ] **Per-key credit limit.** Key creation takes an optional spend cap enforced by
            OpenRouter itself, independent of `PLANTOPIA_DAILY_SPEND_CAP_USD`. Set it to a
            small multiple of that cap, not unlimited — it is the brake that still works if
            the application's own accounting has a bug.
      - [ ] **Data policy / privacy settings.** A diagnosis prompt carries what an owner wrote
            about their plant and, when location is used, roughly where it is growing — the
            same category of sensitive content the LangSmith tracing decision in §3 is about,
            just at the model-provider hop instead of the observability one. OpenRouter's
            privacy settings control whether prompts/completions may be logged by OpenRouter
            and whether routing is allowed to providers whose terms permit training on
            submitted data. Decide this deliberately for a personal account rather than
            inheriting whatever it defaults to.
      - [ ] Re-probe the model slugs (`core/config.py`, already noted in §1.5) once these
            restrictions are in place — a stricter data policy can rule a provider out
            entirely, not just its discounted tier.
      - [ ] **Prompt injection guardrail.** OpenRouter's workspace/key **Guardrails** (Security
            section) run a free, local, regex-based scan — over 30 patterns derived from the
            OWASP LLM Prompt Injection Prevention Cheat Sheet — against every request before it
            reaches the model provider. Relevant here because the diagnosis and chat agents
            build prompts out of things an owner (or, via chat's web search and the plant
            corpus, an outside page) supplied, and neither `api/` nor `agent/` runs any
            injection filtering of its own today. Three modes: `flag` (logged only), `redact`
            (matched span replaced with `[PROMPT_INJECTION]`), `block` (request refused with a
            403); the most restrictive of any workspace- and key-level guardrail that applies
            wins. Start in `flag` mode against real traffic first — OpenRouter's own docs warn
            the patterns are not exhaustive and can false-positive on legitimate input (a
            symptom description quoting a suspicious-looking phrase, for instance) — and only
            move to `redact`/`block` once that rate looks acceptable, using the allowlist for
            any pattern that keeps tripping on legitimate plant-care text.
- [ ] **Alert in GCP when the daily spend cap is actually enforced**, so hitting it is
      something you're told about rather than something a user discovers. Not wired up yet,
      and not quite a one-step Cloud Monitoring alert: `services/limits.check` raises
      `DailyCapReachedError`, and `api/errors.py:_daily_cap` turns it into a `503` — but
      neither logs anything distinguishable. A Cloud Run alert on the 5xx rate would fire on
      *any* 503, not specifically this one. The precise version needs a small code change
      first — a `logger.warning(...)` call in `_daily_cap` naming the cap and the spend — then
      a **log-based metric** in Cloud Logging counting that line, and a **Cloud Monitoring
      alert policy** on that metric (Monitoring → Alerting → Create Policy, or
      `gcloud alpha monitoring policies create`). This is separate from a GCP **billing
      budget** alert (Billing → Budgets & alerts), which watches GCP's own infrastructure
      spend, not OpenRouter usage — worth having too, but answers a different question.

### 2.5 Settings whose defaults are development choices

| Setting | Default | Why it needs a decision |
|---|---|---|
| `PLANTOPIA_APP_URL` | `http://localhost:5173` | Every email link (see 1.4) |
| `PLANTOPIA_DATABASE_URL` | `…@localhost:5433/plantopia` in `core/config.py`; overridden to a Supabase session-pooler URL in this environment's `.env` | The default is the dev container; production points at Supabase instead, not at `db:5432` inside a compose network |
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

### 2.7 An application-level guardrails classifier

**Not built.** §2.4's OpenRouter guardrail is one regex-based check (prompt injection),
applied to every request the key sends account-wide — it does not know this is Plantopia
traffic specifically, and it only looks at what goes *in*, never at what the model hands
back. Nothing in `agent/` or `api/` today checks a chat message or a diagnosis output for
any of the following before it reaches a user or gets stored:

- [ ] **Jailbreak / instruction-override attempts** against the app's own system prompt —
      distinct from OpenRouter's generic injection regex, which is not exhaustive and knows
      nothing about what Plantopia's prompts specifically ask the model to do or refuse.
- [ ] **PII in chat input.** A person describing where a plant lives can end up typing an
      address or a phone number into a message that gets sent to a third-party model and, via
      LangSmith (§3), potentially traced.
- [ ] **Toxic language**, on chat input at minimum — the chat agent is the one place open
      registration puts a live, user-authored message in front of a model on this app's bill.
- [ ] **Topic/scope drift.** The chat agent is meant to answer plant-care questions; nothing
      stops a signed-in account from using it as a general-purpose chatbot on Plantopia's
      OpenRouter spend, which is a cost problem (§2.4) as much as a safety one.
- [ ] **Output format.** The diagnosis pipeline already expects a specific structured shape
      from the model; validating that structurally, and refusing/retrying a malformed one
      before it is stored or shown, catches a schema drift that would otherwise surface as a
      confusing screen rather than a caught error.

One option for all five: [Guardrails AI](https://guardrailsai.com) (`guardrails-ai`, open
source, MIT), which ships exactly these as validators in its Hub — jailbreak detection,
`DetectPII`, `ToxicLanguage`, a topic-restriction validator, and format/schema validation
(its original purpose: wrapping a model call in a `Guard` against a Pydantic/JSON schema,
which fits the diagnosis pipeline's structured output directly). It would sit inside the
LangGraph pipeline itself — around the chat and diagnosis nodes in `agent/` — rather than
only at the FastAPI boundary, since content pulled in mid-pipeline (the corpus, the chat
agent's web search) never passes through `api/`'s request handling at all.

---

## 3. Operational, and worth having before you need it

- [x] **Custom domain.** Done 2026-09-15. `plantopia-ai.com` was registered (Cloudflare) and
      mapped to `plantopia-web` via `gcloud beta run domain-mappings create
      --domain=plantopia-ai.com --region=europe-west1` — at the root, not a subdomain. This
      required moving the frontend service from `europe-west3` to `europe-west1`: Cloud Run's
      native domain-mapping feature does not support `europe-west3` (supported EU regions:
      `europe-west1`, `europe-west4`, `europe-north1`); the API stayed in `europe-west3`, only
      the frontend moved. The old `europe-west3` frontend service was deleted. DNS (4 A + 4
      AAAA records, at `@`, DNS-only in Cloudflare) resolved correctly from the start; Google's
      managed TLS certificate took about an hour to provision (`CertificatePending` →
      `Ready: True` / `CertificateProvisioned: True`, confirmed via `gcloud beta run
      domain-mappings describe --domain=plantopia-ai.com --region=europe-west1`).
      `https://plantopia-ai.com` verified serving both the static frontend and the proxied API
      (`/api/v1/ready` returns `200`). §1.2's same-origin constraint holds — the domain points
      at the same Caddy service doing the same reverse proxy. `PLANTOPIA_APP_URL` updated to
      `https://plantopia-ai.com` and the API redeployed.
- [ ] **Database backups.** One Postgres holds the domain tables, the corpus vectors and both
      LangGraph checkpointers — as of 2026-09-14, Supabase's, not the compose container's.
      Confirm what the project's Supabase plan actually provides (automatic backups and PITR
      are plan-gated) rather than assuming they exist. The compose volume (`pgdata`) now holds
      only dev/test data — a `docker compose down -v` no longer touches a real account, but it
      also means that volume is not where a production backup story lives anymore.
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
- [ ] **Log retention and access.** Production no longer logs live links — `ResendMailer` is
      active there (§1.4). Still true for any environment without a mail key (local dev,
      tests): at `INFO`, `ConsoleMailer` puts password-reset and verification links straight
      into the logs.
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
