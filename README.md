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
- **Retrieves grounding knowledge** from a curated corpus of 43 disorder documents,
  escalating to web search only when the corpus falls short
- **Fetches recent weather** for outdoor plants — a late frost is often the diagnosis
- **Returns a differential**, not a single answer: two or three ranked candidates,
  each with supporting evidence, contradicting evidence, and a test you can run in
  five minutes to tell them apart
- **Builds a dated treatment plan**, least invasive first
- **Warns about contagion** if the problem can spread to your other plants
- **Says when it cannot tell**, instead of guessing

## Getting started

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <your-repo-url>
cd plantopia
uv sync

cp .env.example .env
# add your PLANTOPIA_OPENROUTER_API_KEY

uv run streamlit run app.py
```

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
| `reasoning` | question selection, diagnosis, treatment planning | `anthropic/claude-sonnet-4.5` |
| `embedding` | corpus indexing, query retrieval, and direct photograph matching | `google/gemini-embedding-2` |

Override any of them in `.env`. Check [openrouter.ai/models](https://openrouter.ai/models)
for current slugs — availability and naming change.

The embedding model is multimodal: text and images share one vector space, so a
photograph of the plant can be matched against the corpus directly, not only through
the vision model's written description of it — a second retrieval path that fails
independently of the first (spec §10.4). That is a real constraint on substitution:
swapping in a text-only embedding model gains nothing on cost (the corpus is only
around 300 chunks, so the whole collection indexes for a fraction of a cent) and loses
the photograph-matching path entirely. `qwen/qwen3-embedding-8b` and `baai/bge-m3` are
worth trying only if that trade-off is acceptable for a given deployment.

A Tavily key is optional. Without it, web-search escalation is skipped and diagnosis
relies on the curated corpus alone.

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
              ▼                  ▼                              gather_context
            stop               stop                          ══ interrupt() ══
                                                                       │
                             ┌─────────────────────────────────────────┘
                             ▼
                          enrich ── knowledge base (always)
                             │   ├─ weather        (outdoor plants only)
                             │   └─ web search     (only if retrieval is weak)
                             ▼
                        diagnose ──▶ check_contagion ──▶ build_roadmap ──▶ persist
```

**Two agent architectures, deliberately.** The diagnosis pipeline is an explicit
LangGraph state machine, because two orderings must be guaranteed: identification
precedes diagnosis, and the clarifying-question interrupt always fires. A free-form
ReAct agent asked to do this reliably will sometimes skip a step. Conversational
follow-up has no predictable shape, so it uses a ReAct loop instead.

**When RAG, when search.** The curated corpus is authoritative and reproducible, so it
is consulted first. Web search fires only when the best retrieval score falls below a
threshold or the species could not be identified — the case where the corpus may
simply not cover this plant. Web results are labelled as such in the UI.

**Memory.** Short-term state lives in a LangGraph SQLite checkpointer, which is what
lets the graph pause for your answers and survive a page reload. Long-term memory is
the application's own SQLite tables — plants, observations, diagnoses, roadmap steps —
which is what makes contagion triage possible today and the follow-up flow possible in
Phase 2.

## Safety

- Non-plant uploads are rejected, closing the "upload a person, get medical advice" path
- Retrieved and web content is fenced as untrusted data; instructions found inside it
  are reported, never followed
- Uploads are validated by magic bytes, not filename
- Treatment escalates cultural → mechanical → biological → chemical, and never states
  a dose for a chemical product
- Below a confidence threshold, the agent says it cannot tell and names the evidence
  that would resolve the question

## Development

```bash
uv run pytest                    # unit + graph tests, no network, a few seconds
uv run pytest -m ui --no-cov     # Streamlit AppTest page tests
uv run pytest --cov              # coverage, gated at 85%
uv run ruff check . && uv run ruff format .
```

Unit tests make **no LLM calls and no network calls**. Models arrive through
`core/llm.py`, which tests replace with a scripted fake; HTTP is mocked at the
transport layer with `respx`. Tests assert on structure and control flow, never on
generated prose — model output is not deterministic enough to assert on, even at
temperature 0.

## Project structure

| Directory | Responsibility |
|---|---|
| `ui/` | Streamlit pages and components — rendering only |
| `services/` | The boundary the UI calls |
| `agent/` | Graph, nodes, state, schemas, prompts |
| `tools/` | The seven function tools |
| `knowledge/` | Disorder corpus, ingestion, retrieval |
| `data/` | SQLite schema and repositories |
| `core/` | Config, model factory, guards, image handling |

## Known limitations

- Diagnostic accuracy has not yet been measured against labelled ground truth; that
  is Phase 3
- The corpus covers common houseplant and small-garden disorders. Unusual species fall
  back to web search and generic physiology, with lower confidence
- Single user, no authentication — this runs locally
- Photographs cannot show root condition, so root disorders always depend on the
  confirming test rather than the image

## Design documents

- [`PLAN.md`](PLAN.md) — full design and decisions log
- [`docs/plans/`](docs/plans/) — implementation plans
