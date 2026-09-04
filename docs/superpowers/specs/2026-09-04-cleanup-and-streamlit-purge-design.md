# Cleanup: purging Streamlit, and four carried items

*2026-09-04*

Four lanes of housekeeping, grouped because they share a property: none of them changes
what the application does for anybody using it. One lane removes a dead frontend's
fingerprints, one removes dead code, one closes five small carried items, and one
flattens the file with the most boilerplate in it. The pgvector migration and the Chroma
removal that follows it are deliberately *not* here — see Out of scope.

## Why now

Streamlit was retired two changes into the FastAPI/React migration and the code still
talks about it in the present tense. That is not a cosmetic problem. `services/__init__.py`
says the layer orchestrates "between the Streamlit UI and the diagnosis agent";
`api/__init__.py` says the HTTP interface is "a second client of `services/`, alongside
Streamlit rather than instead of it". Both describe an architecture that has not existed
for weeks, and they are the first thing anybody reads on entering those packages. Six
further sites cite `ui/components/cost_badge.py` and `ui/components/plant_photo.py` as
authorities for a rule — files that are not in the repository.

Worst of the lot is `openspec/config.yaml`, which is loaded as context into every OpenSpec
change. It still names the *current* stack as "Streamlit UI, SQLite domain data, Chroma
vector store" with FastAPI and React as the *target*, describes a `backend/`+`frontend/`
layout that was never built that way, and lists a `ui` pytest marker that `pyproject.toml`
no longer defines. Every future change starts from a briefing that is wrong about the
present.

## What is actually there

325 occurrences of `streamlit`/`Streamlit`/`8501`/`ui/components` across the tracked
files. The figure needs deflating twice before it means anything.

`uv.lock` accounts for 6 of them and they are all the literal string `8501` inside
content hashes. **Streamlit is not a dependency and has not been one** — there is no
`name = "streamlit"` in the lockfile, and nothing in `pyproject.toml`. This lane removes
no dependency and cannot break an install.

Of the remaining 319, **258 sit in dated historical records** and **61 in live code,
configuration, tests and current-state documentation**. Only the 61 are in scope. The
reconciliation is exact: 61 + 258 + 6 = 325.

### The 61 live sites

| Where | Count | Nature |
|---|---|---|
| `docs/code-tour.md` | 31 | Current-state tour of the code |
| `tests/unit/identity/test_message_links.py` | 5 | Regression rationale, plus a live `8501` assertion |
| `.streamlit/config.toml` | 4 | Config for the retired UI; still git-tracked |
| `README.md` | 2 | Current-state documentation |
| 10 source modules | 10 | One comment or docstring each |
| 7 further test files | 7 | One comment or docstring each |
| `.env.example`, `openspec/config.yaml` | 2 | Live configuration |

Every one of the source-module sites is a comment or a docstring. **No executable line in
the application mentions Streamlit**, so this lane cannot change behaviour — a claim the
existing suite is asked to confirm rather than a claim made on inspection alone.

## Three tiers, because "delete every mention" is the wrong instruction for one of them

**Tier 1 — rot. Rewritten or deleted outright.** The docstrings that describe Streamlit as
a live client (`services/__init__.py`, `services/diagnosis_service.py`, `api/__init__.py`)
are rewritten to name the client that actually exists. The six citations of deleted `ui/`
files keep the rule they assert and lose the dangling reference: "never a fabricated
`$0.00`" is a real constraint on `eval/metrics.py`, and it does not need a missing file to
vouch for it. The four sites that explain themselves by comparison to Streamlit's
behaviour (`api/dependencies.py`, `agent/wiring.py`, `agent/studio.py`,
`tests/api/test_app_shape.py`) state their rule directly instead, which is what a reader
who never saw the Streamlit app needs anyway. `.streamlit/` is deleted.
`openspec/config.yaml` is rewritten to the stack that shipped.

**Tier 2 — historical rationale, reworded rather than erased.** Five files name Streamlit
because it *caused* a bug the test now prevents, and the name is load-bearing in a way the
Tier 1 sites are not:

- `tests/unit/identity/test_message_links.py` asserts `"8501" not in settings.app_url`,
  in a test called `test_the_default_address_is_not_a_service_that_was_retired`. Every
  verification and reset email once pointed at `localhost:8501/verify` — Streamlit's port,
  months after Streamlit was retired, at a path the web client has never served. **The
  `8501` assertion stays.** It is a live guard, not a comment, and deleting it would
  remove the only thing standing between that bug and its recurrence.
- `tests/e2e/mail.py`, `web/e2e/people.ts` and `web/e2e/account.spec.ts` explain why the
  browser tests read the real emailed link instead of minting their own token: a
  self-minted link passes while every real one points somewhere that does not exist,
  which is what shipped once.
- `tests/unit/knowledge/test_retriever.py` explains why `Document.id` must be
  deterministic — "every `streamlit run` re-indexed the whole corpus". The mechanism is
  not Streamlit-specific; any restart does it.

These become "a retired UI" and "the previous UI's port". The lesson survives, the brand
name goes, and no assertion moves.

**Tier 3 — dated historical records. Untouched, by decision.** 258 occurrences across
`docs/plans/*.md` (189), `openspec/changes/archive/**` (30), `docs/superpowers/specs/*.md`
(19), `docs/known-limitations.md` (14) and the two course briefs (6).

Rejected: purging these as well, which the instruction "every trace" would literally
require. Three reasons. A dated plan is a record of what was true on the day it was
written, and editing it produces a document that never existed while destroying the
reasoning trail this project has been careful to keep. `docs/known-limitations.md` has an
explicit convention — rows are struck through and dated, never deleted — and a purge would
contradict the file's own stated rule. And `project_brief_capstone.md` and
`project_brief_Sprint4.md` are course briefs that are not ours to rewrite. Raised with the
author on 2026-09-04 and settled: historical records stay.

## Lane 2 — dead code

`recheck_thread` in `agent/threads.py` has had no production caller since the Streamlit UI
was deleted, and has not had one for the whole life of the React frontend: every run now
gets a fresh `diagnosis_thread(user_id)` with a random component, initial or re-check
alike. It is recorded as `M50`. Eight lines across `tests/unit/agent/test_threads.py`
still exercise it, which is why it has stayed green and invisible.

Removed, with its tests. Its docstring carries the `U7` collision story — a derived id of
`recheck-{plant_id}-{diagnosis_id}-{attempt}` built from three values another user could
enumerate — and that story is the reason the current scheme puts the owner in every
handle, so it moves up into the module docstring, which already tells the first half of
it. Deleting a function is not a reason to lose the argument for its replacement.

## Lane 3 — five carried items

**U3, downscaling uploads.** The substantive item. `max_upload_bytes` is 8 MB and
`max_images_per_observation` is 4, so a single diagnosis can send 32 MB of photographs to
the vision model at full resolution. Pillow is already a dependency and `store_upload`
already re-encodes when a photograph needs turning, so this is a cap on the long edge in a
path that is already open. The saving is real and recurring; it was carried originally
because no measurement in this project can see the vision layer (`M19`), which is still
true — so this is justified as cost, and the design deliberately claims nothing about
accuracy.

The cap is **1568 pixels on the long edge**, carried as a new `max_image_edge_px` setting
in `core/config.py` beside `max_upload_bytes` rather than as a module constant, because
every other limit governing an upload is a setting and a reviewer changing one should find
them together. 1568 is the point beyond which the major vision models downscale server
side anyway, so pixels above it are paid for and then discarded. An image already inside
the cap is returned untouched — no re-encode, no quality loss — which keeps the common
case free, exactly as `upright_bytes` already does for a photograph needing no turn.

The ordering constraint in `core/images.py` is the risk. `read_metadata` must run on the
bytes as they arrived, because re-saving destroys an unpredictable part of the metadata
block; the existing test fails if that order is reversed. Downscaling goes *after*
`read_metadata` and alongside `upright_bytes`, inside the same already-tested ordering.

**M52, the Node version.** `.github/workflows/ci.yml` names Node 22 and nothing else does:
no `engines`, no `.nvmrc`, no `volta` key. A laptop and the machine can disagree and the
machine is the one that will be believed. Add both.

**U8, the rejection copy.** `agent/nodes/intake.py:55` interpolates the model's own
sentence raw, producing "This looks like A screenshot of a web form…., not a plant." —
capitalised mid-sentence, with the description's full stop left in. Lowercase the first
character and strip one trailing full stop.

**M13, the hardcoded name.** The register says one occurrence; there are now six
(`agent/nodes/intake.py`, `services/chat_events.py` ×4, `api/errors.py` ×2) and
`settings.app_title` already exists and already defaults to `"Plantopia"`. The
user-facing ones route through it. `core/config.py`'s own default is the one that stays a
literal, being the definition.

**Deleting a plant lands on an error screen.** Found by the owner on 2026-09-04, so it is
not in the register yet. Removing a plant does navigate — `PlantDetail.tsx:148` already
calls `navigate("/")` — and the error still wins, which makes this a bug rather than a
missing feature.

The cause is prefix matching. `keys.plants` is `["plants"]` and `keys.plant(id)` is
`["plants", id]` (`web/src/app/queries.ts`), so `useRemovePlant`'s
`invalidateQueries({ queryKey: keys.plants })` also matches the detail query of the plant
just deleted. That query is still mounted, so it refetches, 404s — and a 404 is on
`QueryProvider`'s permanent list, so it fails immediately without retrying — and
`PlantDetail` renders "This plant could not be loaded".

Two things then make the error stick rather than flash. `useRemovePlant`'s `onSuccess`
*returns* the `invalidateQueries` promise instead of voiding it, and a returned promise is
awaited before the `mutate`-level `onSuccess` runs — so the refetch, the 404 and the error
render all complete *before* `navigate("/")` is reached. Compare `useRenamePlant`
immediately above it, which writes `void queries.invalidateQueries(...)` deliberately.

Fixed with `exact: true` on the list invalidation, so the detail query is never matched;
`void` on it, so navigation is not queued behind a refetch; and `replace: true` on the
navigation, so the back button does not return to a plant that no longer exists.
Deliberately *not* fixed with `removeQueries` on the detail key: the observer is still
mounted at that moment, so removing its query makes it refetch — the same 404 by a
different route.

**M54 is dropped, not deferred.** The item asks that the placeholder replacing cleared
tool output name the tool it cleared. `[cleared]` is the default of LangChain's
`ClearToolUsesEdit`, whose signature is
`placeholder: str = '[cleared]'` — a static string, with no per-call hook. Naming the tool
is not possible through the library, so the item as written cannot be done, and the only
available change is a slightly longer static string that tells a model nothing more. The
register row gets that finding recorded against it instead of a fix.

## Lane 4 — flattening `api/errors.py`

21 handlers, 393 lines, and the same six lines repeated with different constants in most of
them. About 13 are purely `status + type + title + a static detail` and become rows in a
table driven by one registration loop. The other 8 need code and keep explicit handlers:
`UploadRejected` and `MissingAnswerError` read `exc.reason` and `exc.keys`, the quota
handlers add three extras each, `RateLimitedError` sets a `Retry-After` header, and
`RequestValidationError` maps a list of errors.

Expected saving is 100–130 lines. The earlier figure of ~200 was wrong: it assumed the
docstrings went too, and they must not. The "404, never 403 — a 403 asserts the thing
exists and is being withheld, which tells a stranger it exists" reasoning is the most
valuable content in the file. Each table row carries its rationale as a comment. The win
is uniformity — one place where a new failure is added, rather than twenty-one chances to
return a bare string — and the line count is a side effect.

The `type` URIs are a client-facing contract (`web/src/api/problems.ts` branches on them),
so no row may change one. This is a pure refactor: the existing tests in `tests/api/` are
the proof, and any drift shows up as a failure rather than as a review comment.

## Testing

Lanes 1 and 2 change comments, configuration and one deleted function. The suite is the
proof that nothing else moved, and it must stay green with coverage at or above the 85%
gate. Removing `recheck_thread` and its eight test lines moves the coverage denominator, so
the gate is checked rather than assumed.

U3 is the only behavioural change and gets tests first: an oversized image comes back
within the cap, a small one is returned untouched with no needless re-encode, and the
metadata still read from a downscaled upload proves the ordering constraint held. Lane 4
adds no tests and must break none.

`docker compose up -d db` is a prerequisite for the suite (`M26`).

A grep for the pattern over the tracked files is the acceptance check for Lane 1: it should
return 258 in the historical records, 6 hash coincidences in `uv.lock`, and nothing else.

## Out of scope

**Chroma, and the pgvector switch.** `corpus_chunks` and `PgVectorRetriever` exist, are
migrated and are tested, and nothing consumes them; retrieval still runs on Chroma
(`M25`). Removing Chroma is wanted and is queued behind finalising that transition, which
needs the embedding model chosen, fresh embeddings and a new evaluation baseline — none of
which belongs in a change whose defining property is that it moves no numbers.

Designed separately on 2026-09-04, once the embedding-model question was settled by
keeping the current model: see `2026-09-04-pgvector-retrieval-design.md`. That change
rewrites `openspec/config.yaml`'s stack description again, so this one leaves the Chroma
sentence in it alone and corrects only the Streamlit half.

**The large modules.** `data/models.py` (544 lines), `agent/schemas.py` (473) and
`services/run_service.py` (404) are the biggest files in the project. Splitting them was
considered and declined for this change: it is import churn across many callers, and
nothing in the register reports them as painful to work in yet.

**Everything else in `docs/known-limitations.md`.** The open rows not named above stay
open. This change closes four and records why a fifth cannot be closed.

**`M51`, deployment.** No Dockerfile and no application service in `docker-compose.yml`.
That is a decision about where this runs, not housekeeping.
