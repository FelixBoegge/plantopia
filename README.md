# 🌿 Plantopia

An AI plant-health agent. Upload photos of an ailing plant; Plantopia identifies the
species, asks the questions a photograph cannot answer, and returns a ranked
differential diagnosis with an integrated-pest-management treatment plan.

## Why this exists

Plant symptoms are many-to-one ambiguous. Yellowing leaves alone are consistent with
overwatering, underwatering, nitrogen deficiency, insufficient light, root rot, spider
mites, natural senescence and transplant shock. Existing plant apps do one-shot image
classification — they ask nothing, cite nothing, and are confidently wrong often
enough to kill plants.

The information that resolves the ambiguity is not in the photograph. It is watering
cadence, drainage, light hours and recent weather. So Plantopia asks before it
answers, the way a clinician takes a history.

## What it does

- **Rejects non-plant uploads** before anything else runs
- **Identifies the species** and says how confident it is
- **Extracts symptoms with their position** on the plant — interveinal yellowing and
  leaf-tip yellowing have different causes
- **Pauses to ask you two to four questions** chosen for your specific case
- **Reasons before it retrieves.** It shortlists the disorders worth reading about *by
  name*, then fetches those documents from a curated corpus of 43 rather than hoping
  similarity search ranks them — which took the correct document from reaching the
  model in 23 of 28 golden cases to 28 of 28
- **Escalates to web search** only when the corpus falls short
- **Fetches recent weather** for outdoor plants — a late frost is often the diagnosis
- **Returns a differential**, not a single answer: two or three ranked candidates,
  each with supporting evidence, contradicting evidence, and a test you can run in
  five minutes to tell them apart
- **Builds a dated treatment plan**, least invasive first
- **Warns about contagion** if the problem can spread to your other plants
- **Says when it cannot tell**, instead of guessing
- **Remembers every plant.** The My Plants grid shows each plant's own photograph, a
  health badge and its pending roadmap steps; the Plant detail page shows its full
  diagnosis history. A plant is named from the identification the agent made, which you
  can confirm or overwrite.
- **Learns about you, not just your plants.** Durable facts extracted from diagnoses
  and chat — *"tends to overwater"*, *"lives in Berlin"* — are injected as priors into
  later runs. The **What we've learned** page lists each one with its source, confidence
  and last-confirmed date, and forgets any of them on one click — a record of inferences a
  system holds about a person belongs somewhere reachable, not folded under a grid of
  plants.
- **Re-checks progress.** Upload a new photo of a known plant and get a verdict —
  improving, static, worsening, or a new problem — against the prior diagnosis,
  without repeating the clarifying questions: roadmap-step completion already
  answers what was tried.
- **Asks for feedback** once you've actually tried a step, not before.
- **Answers follow-up questions in a chat scoped to one plant**, naming the sources each
  reply consulted on the reply itself, and can flag when a described symptom is
  different enough to warrant a fresh look.

## Getting started

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and Docker.

```bash
git clone <your-repo-url>
cd plantopia
uv sync

docker compose up -d db          # PostgreSQL 17 with pgvector, on port 5433
uv run alembic upgrade head      # create the schema

cp .env.example .env
# add your PLANTOPIA_OPENROUTER_API_KEY

uv run streamlit run app.py
```

**Port 5433, not 5432.** A machine with PostgreSQL already installed has a service on
5432, and on Windows both it and Docker's proxy will bind the port — so connections reach
whichever won, and the symptom is `password authentication failed for user "plantopia"`
from a container that is demonstrably healthy. Publishing elsewhere removes the ambiguity
rather than asking anyone to stop their own database.

**One key, four models.** Everything — chat *and* embeddings — is routed through
[OpenRouter](https://openrouter.ai), which mirrors the OpenAI API shape on both its
`/chat/completions` and `/embeddings` endpoints. Switching providers is a
configuration change rather than a code change, and there is one key and one bill.

The pipeline uses separate tiers because its jobs differ enormously in difficulty, and
the price gap between tiers is often more than tenfold:

| Tier | Used by | Default |
|---|---|---|
| `gate` | the two binary image checks, which run on every diagnosis | `google/gemini-2.5-flash-lite` |
| `vision` | species identification, symptom extraction | `google/gemini-2.5-flash` |
| `reasoning` | question selection, diagnosis, treatment planning | `openai/gpt-4o` |
| `embedding` | corpus indexing and query retrieval | `openai/text-embedding-3-small` |

Every one of those was verified reachable **and tool-calling** on a restricted,
college-issued OpenRouter key. That qualifier matters more than it sounds: a model that
answers a chat request but cannot emit a tool call is useless here, because the whole
pipeline depends on structured output.

### Checking what your key can reach

OpenRouter gates providers by data policy, and organisation-issued keys are often
restricted. A blocked model returns

```
404 No endpoints available matching your guardrail restrictions and data policy
```

which is an **account setting, not a bad slug** — worth knowing before you spend an hour
on the wrong hypothesis. On the key this was developed against, `anthropic/claude-sonnet-4.5`,
`openai/gpt-4.1`, `google/gemini-2.5-pro` and `gemini-embedding-001` were all blocked
while `openai/gpt-4o` and the Gemini Flash models worked. Distinguish the three failure
modes by their message: `No endpoints available matching your guardrail…` is policy,
`Model X does not exist` is a wrong slug, and `No endpoints found for X` is a real slug
with nothing serving it.

`.env.example` lists the stronger models as commented-out upgrades to try if your policy
permits them.

### Cross-modal retrieval is off by default

The design includes a second retrieval path that embeds the photograph itself and
searches the same corpus, bypassing the vision model's written description — two paths
that fail independently (spec §10.4). It needs an embedding model accepting image input,
and none is currently reachable: the OpenAI embedding models refuse images outright
(*"OpenAI embeddings do not support image_url inputs"*), and `gemini-embedding-001`, the
only candidate, is data-policy blocked on restricted keys.

So `PLANTOPIA_MULTIMODAL_EMBEDDINGS` defaults to `false` and diagnosis runs on the text
path alone. The code stays in place and tested; set that flag to `true` alongside a
multimodal `PLANTOPIA_EMBEDDING_MODEL` and the path lights up with no code change.

When it is off, the pipeline says so rather than staying quiet about it. The retriever
reports that it cannot search by image, so the enrich node skips the call and does not
list `search_by_photograph` among the tools used; the diagnose prompt states outright
that no photograph-matched material is available. Both exist because the first live run
showed what silence costs — the model narrated visual corroboration it had never been
given, and the UI credited a search that could not have happened.

A Tavily key is optional. Without it, web-search escalation is skipped and diagnosis
relies on the curated corpus alone.

A LangSmith key is optional too. Without it, tracing is skipped and the app runs
unchanged; with it, every graph run is traced under the configured project.

## Example

> **You upload** three photos of a basil plant with yellowing lower leaves.
>
> **Plantopia asks** how often you water it, whether the pot has drainage holes, and
> how many hours of direct light it gets.
>
> **You answer** every other day, no drainage holes, about three hours.
>
> **Plantopia returns:**
>
> 1. **Overwatering — 65%** · 🟡 Act this week
>    *How to confirm:* push a finger 3 cm into the soil three days after watering. If
>    it is still wet, water is going in faster than the plant can use it.
>    *Points to it:* no drainage holes, watering every other day, yellowing on the
>    oldest leaves, soil wet in the photo.
>    *Argues against it:* the plant is not wilting, and the stem base looks firm.
>
> 2. **Insufficient light — 22%** · 🟢 Monitor
>    *How to confirm:* compare the spacing between new leaves with older growth. Long
>    gaps mean the plant is stretching for light.
>
> **Treatment plan**
> 1. Stop watering until the top 3 cm is dry — *today*
> 2. Repot into a container with drainage holes — *within 3 days*
> 3. Move to your brightest windowsill — *today*

## How it works

```
photos ──▶ guard_input ──▶ quality_check ──▶ identify_plant ──▶ assess_symptoms
              │                  │                                     │
        not a plant         too blurry                                 ▼
              ▼                  ▼                            select_questions
            stop               stop                                    │
                                                                       ▼
                                                              gather_context
                                                           ══ interrupt() ══
                             ┌─────────────────────────────────────────┘
                             ▼
                       hypothesise ── name the disorders worth reading about
                             │
                             ▼
                          enrich ── knowledge base (the shortlist, fetched by name)
                             │   ├─ weather        (outdoor plants only)
                             │   └─ web search     (only if retrieval is weak)
                             ▼
                        diagnose ──▶ check_contagion ──▶ build_roadmap ──▶ persist
```

A re-check of a known plant is the same graph on a different route: `quality_check`
sends it straight to `assess_symptoms`, skipping identification, and `compare_progress`
then either revises the existing roadmap or escalates into the full differential —
through `hypothesise`, so an escalating re-check reads the same shortlist a first
diagnosis would. [`docs/agent-graph.md`](docs/agent-graph.md) has both graphs drawn from
the code itself, so they cannot quietly disagree with it.

**Two agent architectures, deliberately.** The diagnosis pipeline is an explicit
LangGraph state machine, because two orderings must be guaranteed: identification
precedes diagnosis, and the clarifying-question interrupt always fires. A free-form
ReAct agent asked to do this reliably will sometimes skip a step. Conversational
follow-up has no predictable shape, so it uses a ReAct loop instead.

**When RAG, when search.** The curated corpus is authoritative and reproducible, so it
is consulted first. Web search fires only when the best retrieval score falls below a
threshold or the species could not be identified — the case where the corpus may
simply not cover this plant. Web results are labelled as such in the UI.

**Why a model names the disorders before retrieval runs.** Similarity search answers
"which corpus text resembles this description", which is not the question "what could be
wrong with this plant". On the nutrient cases the two came apart badly: the owner's words
(*"faded to a flat, dull yellow"*) and the corpus's (*"uniform pale green or yellow, veins
included"*) are not near neighbours, and the correct document sat at rank 16, 17 and 21 of
43 — far enough down that no reordering of six results reaches it. The `hypothesise` node
asks the model to name candidates from the list of ids the corpus actually holds, and
`enrich` fetches those by name. Rank stops mattering once you can look something up by
name. It is a shortlist for *reading*, never a conclusion: nothing there writes to the
differential, and `diagnose` is free to reject every hypothesis it offered. If the call
fails the pipeline falls back to similarity search alone.

**Memory.** Short-term state lives in a LangGraph Postgres checkpointer, which is what
lets the graph pause for your answers and survive a page reload — or a redeploy. Long-term
memory is the application's own tables — plants, observations, diagnoses, roadmap steps
and learned facts about the owner — which is what makes contagion triage, the re-check
flow and the learned profile possible. Both live in the same PostgreSQL, along with the
photographs themselves.

Both graphs share one checkpointer. They used to have a SQLite file each, because the
diagnosis one grew by ~100 MB per run: graph state carried whole photographs as base64
and LangGraph re-serialises state at every superstep. State carries blob keys now, so a
completed diagnosis leaves under a kilobyte behind and there is nothing to keep apart.
What does keep runs apart is the thread id, which carries its owner — a handle resumes a
paused diagnosis that has already been paid for, so it is checked before use.

## Safety

- Non-plant uploads are rejected, closing the "upload a person, get medical advice" path
- Retrieved and web content is fenced as untrusted data; instructions found inside it
  are reported, never followed
- Uploads are validated by magic bytes, not filename
- Treatment escalates cultural → mechanical → biological → chemical, and never states
  a dose for a chemical product
- Below a confidence threshold, the agent says it cannot tell and names the evidence
  that would resolve the question
- Every chat reply names the sources it consulted, on the reply rather than behind a
  click, and the agent is told to admit when it answered from its own knowledge instead of
  a lookup — a grounded answer should be distinguishable from an ungrounded one at a
  glance. An empty lookup points it at web search rather than back at its memory

## Development

```bash
docker compose up -d db          # a prerequisite: the suite uses a real database
uv run pytest                    # unit + graph tests, ~1.5 minutes
uv run pytest -m ui --no-cov     # Streamlit AppTest page tests
uv run ruff check . && uv run ruff format .
```

1,024 tests in the gated run at 95% coverage (gated at 85%), plus 97 in the `ui` tier.

**Tests make no LLM calls.** That constraint is absolute: models arrive through
`core/llm.py`, which tests replace with a scripted fake, and HTTP is mocked at the
transport layer with `respx`. Tests assert on structure and control flow, never on
generated prose — model output is not deterministic enough to assert on, even at
temperature 0.

They do talk to a database. The suite used to advertise "no network calls" as well, and
that claim is retired rather than quietly falsified: repository, blob-store, retriever and
checkpoint tests run against real PostgreSQL in a container, on a throwaway database
created per session and dropped afterwards, each test inside a transaction that is rolled
back. Mocking the database in a project whose subject is the database would produce tests
that assert on the mock.

**Run the `ui` tier separately whenever you touch a page or component.** `ui/pages/*`,
`ui/components/*` and `ui/bootstrap.py` are omitted from coverage, because counting
untestable wiring as a gap made the gate trip on unrelated changes. They are meaningfully
tested — just in the `-m ui` tier, which the gated run deselects. So the gate cannot catch
an untested page; only that second command can.

### Opening the graphs in LangGraph Studio

```bash
uv run langgraph dev --studio-url https://eu.smith.langchain.com
```

Serves both graphs from `langgraph.json` on `http://127.0.0.1:2024` and renders them in
Studio, where you can run a thread, stop at the interrupt, inspect state at every step and
fork from any point. `--studio-url` is not optional: this project's LangSmith key is on the
**EU** instance and the CLI defaults to the US one, where it silently shows nothing.
`langgraph dev` loads `.env`, so running a thread there costs real money — looking at the
diagram does not. See [`docs/agent-graph.md`](docs/agent-graph.md) for the details.

### Evaluation

```bash
uv run python -m eval.run_eval
```

Runs the golden-set harness against a real model — question selection, differential
diagnosis and retrieval, scored for top-1/top-3 accuracy and Ragas retrieval metrics,
with the same case run several times to measure how stable the diagnosis is under
byte-identical input. It takes several minutes and makes real, billed model calls, so
it is never invoked by the test suite or by the app itself. It writes a timestamped
JSON file to `eval/results/` and a human-readable `eval/REPORT.md`.

Where it currently stands, over 28 golden cases (2026-08-19, `overwaterer` profile — see
`--profile` below):

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 89.3% |
| Top-3 diagnostic accuracy | 96.4% |
| Top-1 agreement on byte-identical input | 100.0% |

Every category reaches 100% at top-3 except `other`, which is two cases. Of the three
top-1 misses, one landed on a disorder its own case listed as a confusable neighbour.
Reasoning before retrieval (`hypothesise`) is what moved top-1 from 75.0% to 89.3%, and
took nutrient deficiencies — the category that used to fail at 33.3% on *both* top-1 and
top-3 — to 100% at top-3.

All four Ragas metrics now score all 28 rows. Earlier runs lost roughly half the judge
calls to dropped connections and averaged over whatever survived, so figures from before
that fix are not comparable with these. `eval/REPORT.md` carries the full table, the
per-metric row counts, and a **What this does not measure** section — the short version
being that golden cases inject symptoms as text, so none of these numbers say anything
about the vision layer.

```bash
uv run python -m eval.run_eval --profile overwaterer
```

`--profile` injects a fixture from `eval/profiles/` as a run-level prior, the same
block a real owner's learned facts would produce, so the harness can measure whether
the profile moves diagnosis rather than just trusting that it does. It defaults to
`empty`, which renders as no block at all. Two such runs are recorded in
`docs/known-limitations.md`: an empty profile reproduces the Phase 3 baseline exactly,
and a deliberately lopsided one changes candidates and clarifying questions on a
minority of cases without pulling any category's top diagnosis toward the biased
disorder.

Both of those gates predate `hypothesise`, and no neutral-profile run has been made since
it landed — so the table above is a lopsided-profile run, and the 75.0% → 89.3% lift is
measured between two `overwaterer` runs rather than against the `empty` baseline. That
keeps the comparison clean but leaves the current neutral figure unmeasured; an `empty` run
is the cheapest thing to do next.

The **Evaluation** page in the app renders whatever the newest file in `eval/results/`
contains; it only reads that file and never runs the harness itself. Before the first
run, the page says so explicitly and names the command above, rather than showing a
traceback or a blank page.

`ragas` and `pyyaml`, used only by the harness, are `dev`-dependency-group packages —
the shipped app never imports them.

## Project structure

| Directory | Responsibility |
|---|---|
| `ui/` | Streamlit pages and components — rendering only |
| `services/` | The boundary the UI calls |
| `agent/` | Both graphs, nodes, state, schemas, prompts |
| `tools/` | The seven function tools |
| `knowledge/` | Disorder corpus, ingestion, retrieval |
| `data/` | Models, repositories, Alembic migrations |
| `core/` | Config, model factory, guards, image handling, cost, tracing |
| `eval/` | Golden set, harness, metrics, report renderer |
| `tests/` | `unit/`, `graph/` and `ui/` tiers |
| `docs/` | Graph diagrams, code tour, plans, limitations |

## Known limitations

- **The vision layer is unmeasured.** Golden cases supply symptoms as text and are
  injected past `identify_plant` and `assess_symptoms`, so no number in `eval/REPORT.md`
  says anything about species identification or symptom extraction from a photograph.
  Diagnosis is stable on byte-identical *text*; the one badly unstable run on record
  differed in its photographs, which makes vision the prime suspect and the measurement
  most worth buying next
- The corpus covers common houseplant and small-garden disorders. Unusual species fall
  back to web search and generic physiology, with lower confidence
- Single user, no authentication — the schema is multi-tenant and every query is scoped to an owner, but there is one seeded owner and no way to become a different one yet
- Photographs cannot show root condition, so root disorders always depend on the
  confirming test rather than the image
- **Chat context grows without bound.** Every turn replays the whole conversation to the
  model, and checkpoints are never pruned. Chat token usage is not tracked at all
- Uploads are not downscaled before they reach the vision model. Storage is no longer the
  reason to care — photographs live in the database once rather than in every checkpoint —
  but a full-size image is still sent to the vision tier on every diagnosis, and that is
  cost. Left alone deliberately: downscaling changes what the model sees, and nothing here
  can measure the vision layer
- **The corpus is in two places and only one is used.** `corpus_chunks` holds all 301
  sections in pgvector, and retrieval still runs on Chroma. The move waits until the
  embedding model is chosen, since a different model means re-embedding anyway

A fuller accounting — every gap raised in review, why it was carried, and what fixing it
would take — is in [`docs/known-limitations.md`](docs/known-limitations.md).

## Design documents

- [`project_brief_Sprint4.md`](project_brief_Sprint4.md) — the sprint-4 assignment
  this was built against
- [`docs/agent-graph.md`](docs/agent-graph.md) — both graphs, drawn from the code, and how
  to open them in LangGraph Studio
- [`docs/code-tour.md`](docs/code-tour.md) — a reading order through the codebase
- [`docs/plans/`](docs/plans/) — implementation plans
- [`docs/known-limitations.md`](docs/known-limitations.md) — carried work and non-goals
- [`eval/REPORT.md`](eval/REPORT.md) — the newest evaluation run in full
