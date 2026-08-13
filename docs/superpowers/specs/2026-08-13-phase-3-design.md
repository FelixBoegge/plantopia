# Phase 3 Design — Observability, Cost, and Evaluation

**Status:** approved, implementation plan not yet written.

**Companion documents:** [`PLAN.md`](../../../PLAN.md) §15, §16, §17 describe the target design this
phase builds toward, and §20 lists the two optional-task claims it makes good on.
[`docs/known-limitations.md`](../../known-limitations.md) supplies most of the constraints below —
notably `M12` (the cost columns nothing writes) and the diagnostic-stability finding that motivates
the evaluation harness. [`docs/code-tour.md`](../../code-tour.md) §3c.6 explains the single-write
transaction this phase must not break.

---

## 1. Scope

Two features that share one theme — making the system measurable — and, usefully, one mechanism:
LangSmith tracing and cost capture are both LangChain callbacks, so they attach at the same seam and
the wiring is written once.

- **LangSmith tracing** (`PLAN.md` §15, Hard 2) — optional, degrading when no key is present.
- **Token and cost capture and display** (`PLAN.md` §15, Medium 1, `C15`) — which is the `M12` fix.
- **Ragas evaluation** (`PLAN.md` §16, Hard 3) — a text-first golden set, a CLI harness, a committed
  report, and the in-app Evaluation page.

The bonus threshold (2 medium + 1 hard) is already met by shipped work, so everything here is
portfolio strength rather than a pass condition. That makes cutting cheap, and it is the reason the
scope below is drawn tightly.

**Explicitly out of scope for this phase**, and why:

| Item | Disposition |
|---|---|
| Learned user profile (`C16`, `PLAN.md` §11.3) | **Phase 4.** Deferred once already by the Phase 2 spec, and for the same reason: it is cross-cutting — extraction after every session, injection into every prompt — rather than self-contained, so it earns its own spec rather than riding along with two features it shares no code with. |
| Chat token/cost tracking | **Dropped, and recorded as a limitation.** `messages` has no cost columns, and adding them means introducing the project's first schema migration path against Phase 2's deliberate no-migration property. Chat spend is small next to a vision-plus-reasoning diagnosis. Goes into `known-limitations.md` as an explicit gap rather than silence. |
| Vision-layer accuracy | **Structurally unmeasured.** The golden set injects past the vision nodes (§3), so no metric here says anything about species identification or symptom extraction. Stated plainly in the report rather than implied by an end-to-end number. |
| `M15` / `M16` (checkpoint growth) | **Carried again.** This phase adds nothing to graph state, so it makes neither worse. |
| Live evaluation from the UI | **Dropped.** A full run takes minutes and real money; it belongs behind a CLI. The page renders committed results (§4). |

---

## 2. Observability

### 2.1 One seam, two consumers

```
build_chat_model  ──►  extra_body gains {"usage": {"include": true}}
                       one line, covers all three tiers
        │
        ▼
  every model call  ──►  UsageCollector (BaseCallbackHandler, run-scoped)
                          accumulates {tier: (prompt_tokens, completion_tokens, cost)}
        │
        ▼
  DiagnosisService  ──►  config = {"callbacks": [collector],
                                   "configurable": {"thread_id": …,
                                                    "usage_collector": collector}}
        │
        ▼
     persist(state, config)  ──►  collector.snapshot()
                                  written inside the transaction it already owns
```

The collector is passed **twice on purpose**: as a callback so it observes every model call
automatically — including calls from nodes nobody remembered to instrument — and through
`configurable` so `persist` can read it. `persist` is a graph node, so it cannot see a callback
object any other way, and by the time it runs every model call in the run has completed.

**This carries one assumption that must be verified before it is depended on:** that LangGraph
passes a non-JSON-serialisable object through `configurable` to a node *and* that checkpointing does
not try to serialise it. The implementation plan opens with a spike that proves both against the
real `SqliteSaver`. If it fails, the documented fallback is a `contextvars.ContextVar` set by the
service for the duration of the run — run-scoped, invisible to the checkpointer, and read by
`persist` through a `current_collector()` accessor in `core/cost.py`.

### 2.2 Why not the alternatives

Two rejected designs, recorded because both are tempting:

- **Usage accumulated in graph state** — each model-calling node appends its `usage_metadata` to a
  state field. Explicit and inspectable, but it touches roughly seven nodes, grows the state that
  `M15` already blames for ~100 MB of checkpoint per diagnosis, and any node added later that
  forgets to append is silently unmetered.
- **A post-run `UPDATE` from the service** — smallest diff by far, but it splits one write into two
  transactions. A crash between them leaves a diagnosis row with `NULL` cost, which is precisely the
  state `M12` describes today, and it contradicts the single-transaction design `code-tour.md` §3c.6
  spends a section justifying.

### 2.3 Cost truth comes from OpenRouter

`PLAN.md` §15 specified "a cost figure from a configured price table". That was written before the
project committed to routing every call through OpenRouter, which reports the credits it actually
charged per call. Reading the biller's own number removes a hand-maintained rate table that would go
stale silently every time a price changes or a model is swapped via `.env`.

**This requires one verification step before the design depends on it**, in the same spirit as the
model-slug probing documented in `.env.example`: confirm that OpenRouter's per-call cost survives
`ChatOpenAI` into `response_metadata`. If it does not surface cleanly, the fallback is `PLAN.md`
§15's configured price table — the same collector, different arithmetic, no other change.

### 2.4 Tracing

`core/tracing.py` exposes one function that enables LangSmith when a key is present and no-ops
otherwise, following the `PLANTOPIA_TAVILY_API_KEY` precedent: a fresh clone runs unchanged without
one. Because LangChain's tracer is itself a callback, tracing needs no wiring beyond configuration —
every graph node, tool call, retrieval and model call appears automatically, which is the property
`PLAN.md` §15 chose LangSmith for.

### 2.5 Files

| File | Change |
|---|---|
| `core/cost.py` | **new** — `UsageCollector(BaseCallbackHandler)`, per-tier accumulation, `snapshot()` returning a frozen total |
| `core/llm.py` | add `"usage": {"include": True}` to the existing `extra_body` |
| `core/tracing.py` | **new** — enable LangSmith when configured, no-op otherwise |
| `core/config.py` | `langsmith_api_key: str \| None`, `langsmith_project` |
| `services/diagnosis_service.py` | build a collector per run; extend the existing `_config()` |
| `agent/nodes/persist.py` | `persist(state, config)` — snapshot, pass to `diagnoses.create()` |
| `data/repositories/diagnoses.py` | `create()` **already accepts** `token_usage`/`cost_usd` and writes both columns — nothing ever passes them. Only `DiagnosisRecord` changes, gaining `token_usage`; `cost_usd` is already on it. |
| `ui/components/cost_badge.py` | **new** — renders tokens and cost |

The re-check graph reuses `persist`, so re-checks get cost capture with no second wiring point.

---

## 3. Evaluation

### 3.1 The golden set is text-first, and the reason matters

`PLAN.md` §16 proposed PlantVillage-style images. That dataset is crop leaf pathology — tomato,
potato, corn — while this corpus is 43 houseplant and ornamental disorders dominated by watering,
light and nutrient problems. `known-limitations.md` already records the mismatch. Scoring against
such a set would measure corpus scope rather than agent quality.

More decisively: every metric §16 asks for except top-1/top-3 is a **retrieval and generation**
metric. None of them can see the vision layer. So the golden set supplies symptoms as text and
injects past vision, which makes cases authorable in hours rather than days, makes every run
byte-identical in its input, and costs only reasoning-model calls.

The price is that vision accuracy goes unmeasured. That is stated in the report, not hidden.

### 3.2 Case format

25–30 cases in `eval/golden_set/`, **one YAML file per case** — mirroring `knowledge/corpus/`'s
one-document-per-disorder convention, so cases diff and review individually.

```yaml
id: yellowing-lower-leaves-wet-soil
category: watering                # drives the per-category breakdown
plant: {name: "Ficus", species: "Ficus elastica", location_kind: indoor}
species_confidence: 0.82
symptoms:                         # what the scripted vision tier returns, a SymptomSet
  overall_vigor: declining
  soil_condition: "wet, dense, slow to drain"
  symptoms:
    - {description: "uniform yellowing of the oldest leaves",
       position: lower_leaves, severity: act_this_week}
    - {description: "soft brown patches at the leaf base",
       position: whole_leaf, severity: act_this_week}
answers:                          # keyed by clarifying-question key
  drainage: "no drainage holes"
  watering_frequency: "twice a week"
default_answer: "not observed"
ground_truth: overwatering        # must resolve to a corpus disorder slug
also_acceptable: [poor-drainage, root-rot]
```

`ground_truth` is scored against `Candidate.disorder_id`, which is already the corpus slug — so
scoring is an identifier comparison, not name-matching fuzz. `also_acceptable` exists because
several corpus disorders are genuinely confusable (`PLAN.md` §16 predicts failure will concentrate
among nutrient deficiencies), and a top-1 miss onto a listed neighbour is worth reporting separately
from a miss onto something unrelated.

### 3.3 The harness dispatches on schema, not order

`eval/scripted.py` provides a model that returns objects **keyed by the schema requested**:
`PlantCheck` → pass, `ImageQuality` → usable, `SpeciesGuess` → the case's species, `SymptomSet` →
the case's symptoms.

This is deliberately unlike `tests/fakes/chat_models.py`'s `ScriptedStructuredModel`, which replays
a positional queue. `route_after_quality` branches — a re-check of an unidentified plant calls
`identify_plant`, a fresh diagnosis may not — and a positional queue desynchronises on the branch.
Schema dispatch is order-independent. It also means `eval/` needs no import from `tests/`, keeping
the dependency direction right.

Everything else in the run is real: real reasoning model, real retriever, real corpus, real graph,
real interrupt.

### 3.4 Clarifying questions drift, and the harness records it

Clarifying questions are model-generated, so the set asked can differ between runs of the same case.
The harness answers by key and falls back to `default_answer` for anything unmatched, and **records
the questions actually asked on every run**.

This is not a detail. Question drift is itself a variance source, and the stability numbers (§3.5)
would be quietly contaminated by it. The report shows the drift alongside the variance so the two
can be told apart.

### 3.5 Metrics

| Metric | Source |
|---|---|
| Context precision / recall | Ragas, over `state.retrieved` |
| Faithfulness | Ragas, over the differential's `reasoning` |
| Answer relevancy | Ragas |
| **Top-1 / Top-3 accuracy** | ours — `disorder_id` vs `ground_truth` (+ `also_acceptable`) |
| **Stability** | ours — 8 cases × 5 runs: top-1 agreement rate, and Jaccard churn across candidate sets |

Ragas is wired to existing infrastructure via `LangchainLLMWrapper(build_reasoning_model())` and
`build_embeddings()`, both already verified reachable on the restricted key, so this needs no new
model access.

**Stability is measured on a subset rather than the whole set** because 8 × 5 is statistically
adequate for an "is the top candidate stable" claim while keeping the extra cost bounded. It exists
because of a specific recorded finding: re-running the same two photographs produced Root Rot 60% on
one run and Rust 60% on the next, with opposite treatment plans. `default_temperature` is `0.2`, so
variance is expected in kind — its magnitude is what is unknown, and this is what quantifies it.

### 3.6 Outputs

`eval/run_eval.py` (CLI) writes `eval/results/<timestamp>.json` and regenerates `eval/REPORT.md`.

The results file records **run provenance** — model slugs, temperature, corpus document count,
golden-set size, timestamp. A metrics table without the configuration that produced it is not
reproducible, and this report is meant to be read months later.

`REPORT.md` carries the headline metrics, the per-category breakdown §16 asks for, the stability
section, and an explicit **"what this does not measure"** naming the vision layer.

### 3.7 Budget

Roughly 90 pipeline calls for the main set, ~120 for the stability subset, and ~120 Ragas judge
calls — a few dollars and several minutes per full run. Cheap enough to re-run, expensive enough to
justify keeping it out of the UI.

### 3.8 Files

`eval/{__init__,cases,scripted,harness,metrics,ragas_metrics,report,run_eval}.py`,
`eval/golden_set/*.yaml`, `eval/results/`, `eval/REPORT.md`.

`metrics.py` and `ragas_metrics.py` are separate on purpose: accuracy and stability are pure
functions over completed runs and stay fully unit-tested offline, while every Ragas metric needs a
judge model and an embedder. Merging them would put a network dependency into the one module that
has no reason to have one.

---

## 4. UI

**`ui/components/cost_badge.py`** — a `st.caption`-sized badge reading `1,240 in / 890 out ·
$0.0043`, shown in the diagnosis result view in `diagnose.py` and per-diagnosis on the Plant detail
timeline. It reads the new `DiagnosisRecord` fields, so re-checks display it automatically.

**`ui/pages/evaluation.py`** — reads the newest file in `eval/results/` and renders the provenance
header, the headline metrics table, the per-category breakdown as a native `st.bar_chart`, the
stability section, and the "what this does not measure" note. No new charting dependency.

**`app.py`** — register the page in `st.navigation`, matching `PLAN.md` §17's planned structure.

---

## 5. Error handling

Following the project's established "degrade, do not stop" pattern (`code-tour.md` §3b.2):

| Condition | Behaviour |
|---|---|
| No LangSmith key | Tracing off. One INFO log at startup; nothing else changes. |
| OpenRouter omits `cost` | Tokens stored, `cost_usd` stays `NULL`, badge renders tokens only — never a fabricated `$0.00`. |
| No usage observed at all (scripted models in tests) | `snapshot()` returns `None`; `create()` writes `NULL`. Exactly today's behaviour, no crash. |
| `eval/results/` missing or empty | The Evaluation page shows an explicit empty state naming the command to run, not a traceback. |
| Malformed golden case | The loader raises at load time naming the file — failing at the suite rather than at runtime, the philosophy `test_corpus_coverage.py` already uses. |
| One Ragas metric fails | Recorded as `null` for that case; the run continues. The report states how many metrics failed rather than quietly averaging over fewer cases. |
| One case fails mid-pipeline | Recorded as a failure row; the run completes. |

---

## 6. Testing

| Tier | Coverage |
|---|---|
| unit | `UsageCollector` accumulation across tiers and empty-snapshot → `None`; tracing enabled vs no-op; `extra_body` carries the usage flag; `persist` writes usage when the collector is in config and `NULL` when it is not; repository round-trip including `NULL`; schema-dispatch model returns the right object per schema and raises on an unknown one; top-1/top-3 scoring including `also_acceptable`; stability maths on synthetic input; report rendering from a fixture results file |
| unit (structural) | **Every `ground_truth` and `also_acceptable` slug resolves to a corpus document**, and every `category` comes from a fixed vocabulary. This is the golden-set analogue of `test_corpus_coverage.py`: a case referencing a disorder that does not exist fails the suite rather than scoring zero at runtime. |
| graph | A full run with a collector wired persists non-null usage. |
| ui | `evaluation.py` renders a fixture results file and its empty state; `cost_badge` renders tokens+cost, tokens-only, and nothing. |

No test above touches the network. The real harness runs only via the CLI.

### 6.1 Build configuration

- **`ragas` and `pyyaml` go in the `dev` dependency group**, not `project.dependencies`. The shipped
  app imports neither — the Evaluation page reads JSON — and Ragas pulls a heavy transitive tree.
  The runtime footprint stays unchanged.
- `[tool.coverage.run] source` gains `"eval"`. The scoring and stability arithmetic is exactly the
  kind of logic that must be right.
- `eval/run_eval.py` joins `omit`, on `ui/bootstrap.py`'s precedent: it is the network entry point
  and wiring, with everything beneath it unit-tested.

---

## 7. Decisions log

| Decision | Alternative rejected | Why |
|---|---|---|
| Collector passed as callback **and** through `configurable` | Usage in graph state; post-run `UPDATE` | Keeps `persist`'s single transaction (`code-tour.md` §3c.6), adds nothing to state (`M15`), and instruments nodes nobody remembered. |
| Cost from OpenRouter's reported usage | Configured price table (`PLAN.md` §15) | Truth from the biller never drifts. Table retained as the documented fallback if the field does not survive `ChatOpenAI`. |
| Diagnosis cost only | Chat cost persisted; chat cost in-session | Chat columns require the project's first migration, against Phase 2's no-migration property, for a figure dwarfed by diagnosis cost. |
| Text-first golden set | PlantVillage subset; per-case sourced images | Every Ragas metric is a retrieval/generation metric; PlantVillage's crop pathology does not match a houseplant corpus. Vision accuracy is declared unmeasured. |
| Schema-dispatch scripted model in `eval/` | Reuse `tests/fakes/chat_models.py` | A positional queue desynchronises on `route_after_quality`'s branch, and `eval/` should not import from `tests/`. |
| Stability on an 8 × 5 subset | Whole set repeated; accuracy only | Adequate for the claim, bounded in cost, and it answers a finding already recorded in `known-limitations.md`. |
| Evaluation page renders committed results | Live re-run button | A full run is minutes and real money; the report is more valuable as a reviewable artefact in git. |

---

## 8. Open follow-ups (not blocking this phase)

- **Learned user profile (`C16`)** — Phase 4. The `user_profile` table has existed since Phase 1 and
  still has no repository.
- **Chat cost tracking** — needs a migration path. Revisit if a migration is ever wanted for another
  reason.
- **Vision-layer accuracy** — would need the image-sourcing job this phase declined. `PLAN.md` §10.5
  already parks a related question (a reference-image corpus) behind "revisit once the evaluation
  harness can measure whether it actually helps" — after this phase, that harness exists.
- **`M15`/`M16` checkpoint growth** — untouched, and now the largest carried limitations.
