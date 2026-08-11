# Phase 2 Design — Plant Profiles, Re-check, Feedback, and Chat

**Status:** approved, implementation plan not yet written.

**Companion documents:** [`PLAN.md`](../../../PLAN.md) §7–§9, §11, §12 describe the target design this
phase builds toward. [`docs/known-limitations.md`](../../known-limitations.md) and
[`docs/code-tour.md`](../../code-tour.md) describe what Phase 1 actually built and carried, and are
the source of most of the constraints below.

---

## 1. Scope

One combined phase covering four features that share enough surface (the same repositories, the
same Plant detail page, the same graph) to design and build together:

- **Plant profiles UI** — the My Plants grid and the Plant detail page (`PLAN.md` §12).
- **The re-check graph** — the hero feature (`PLAN.md` §7): re-photograph a known plant, get a
  verdict against the prior diagnosis, and a revised roadmap.
- **Treatment-outcome feedback** — C11, backed by the `feedback` table.
- **The chat agent** — a ReAct loop scoped to one plant (`PLAN.md` §8).

**Explicitly out of scope for this phase**, and why:

| Item | Disposition |
|---|---|
| LangSmith tracing, token/cost display, Ragas evaluation | Phase 3. Matches `PLAN.md` §21's descope order (first three items cut) and is a clean split from the four features above, which are all on §21's "must survive" list. |
| Learned user profile (C16, `PLAN.md` §11.3) | Deferred, **not shelved** — long-term memory of user preferences and behaviour patterns (e.g. "tends to overwater") is wanted as a real feature. It is cross-cutting (extraction after every session, injection into every prompt) rather than self-contained, so it lands cleaner as its own pass once these four features are stable. Flag for the next planning conversation after this phase ships. |
| `create_care_schedule` chat tool | Dropped. `roadmap_steps.diagnosis_id` is `NOT NULL`, so there is no way to insert a diagnosis-less, chat-initiated schedule without a schema change. Chat can still discuss and explain the existing roadmap. Revisit only if ad-hoc scheduling becomes a real user need. |
| `M15` (checkpoint DB growth) | Carried further. Re-check compounds it (the pipeline now runs more than once per plant), so this phase avoids making it *worse* (see §3 below) but does not fix it. |

Two carried limitations **are** fixed as part of this phase, because this phase is what first
exercises the code paths they sit in:

- **`M10`** — `RoadmapRepository.mark()` currently no-ops silently on an unknown `step_id`. This
  phase wires a UI checkbox directly to it, so it gets a `rowcount` check that raises instead.
- **`U7`** — the original wizard's `rejected`/`retake` paths don't rotate `thread_id`. The re-check
  entry point reuses `guard_input`/`quality_check`, so it inherits the same reject/retake behaviour;
  fixing it once (rotate on both paths, in the shared service code) covers both entry points.

---

## 2. Data layer

**No schema migration.** Phase 1 built the full schema from `PLAN.md` §11.2 up front — `feedback`,
`user_profile`, and `messages` already exist in `data/schema.sql` — specifically so later phases
wouldn't need one. This phase adds repositories and consumers for tables that already exist, plus
the one behavioural fix:

- `data/repositories/feedback.py` — `FeedbackRepository`, following the existing repository
  conventions (§4.5 of the code tour): write methods take a connection and don't commit, reads
  return frozen dataclasses. `create(diagnosis_id, rating, did_it_help, free_text, now)`, and a read
  method the Plant detail page uses to avoid re-prompting for feedback already given.
- `data/repositories/messages.py` — `MessageRepository`, same conventions. `create(plant_id, role,
  content, tool_calls_json, now)`, `list_for_plant(plant_id)` for reloading chat history.
- `data/repositories/roadmap.py` — `RoadmapRepository.mark()` gains a `cursor.rowcount` check,
  raising (e.g. `ValueError`) when `step_id` doesn't match a row. This is the `M10` fix.

`user_profile` is left untouched this phase (no repository yet) — reserved for the deferred
learned-user-profile work.

---

## 3. The re-check graph

**One unified `StateGraph`**, extending `agent/diagnosis_graph.py` — not a second compiled graph.
`PLAN.md` §7 describes the re-check flow as "a second entry point into the same graph," and a single
`StateGraph` with conditional routing is the literal way to build that, while also being the only
option that lets a `worsening`/`new_problem` verdict fall through into a genuine full re-diagnosis by
rejoining the existing chain rather than re-implementing it.

### 3.1 Entry and routing

`services/diagnosis_service.py` gains `start_recheck(plant_id, uploads, ...)`, which builds the
initial `DiagnosisState` with `plant_id` and `species` **already populated** from the existing plant
record (read via `PlantRepository.get`, one of the `M11` methods this phase puts to use). Because
`species` is already set, `identify_plant`'s existing idempotency guard (`if state.species is not
None: return {}`) already does the right thing — but the router is changed to skip the node
entirely for a re-check, matching `PLAN.md` §7's diagram rather than relying on the guard as
anything but a backstop.

A new router, added after `quality_check`, replaces the current unconditional edge to
`identify_plant`:

```
quality_check ──(continue, plant_id is None)──▶ identify_plant ──▶ assess_symptoms ──▶ ...
              ──(continue, plant_id is set)───▶ assess_symptoms ──▶ compare_progress
```

### 3.2 New nodes

- **`compare_progress`** (`agent/nodes/recheck.py`) — reads the prior diagnosis and roadmap status
  **live**, via `deps.diagnoses.latest_for_plant(state.plant_id)` and
  `deps.roadmap.list_for_plant(state.plant_id)` (both existing, unused-until-now `M11` methods),
  rather than carrying the prior differential through graph state. This matters for `M15`: state
  that LangGraph re-checkpoints at every superstep should not gain a second full differential on
  top of the base64 images it already carries. Produces a new `ProgressVerdict` schema
  (`verdict: Literal["improving", "static", "worsening", "new_problem"]`, plus reasoning and the
  evidence that drove the call) via structured output, following the existing `invoke_structured`
  pattern (§2.5 of the code tour).
- **`revise_roadmap`** (same module) — for `improving`/`static` verdicts, produces revised roadmap
  steps without re-running `diagnose`. This is a model call, not a deterministic rule like
  `check_contagion`: tapering a roadmap or escalating one IPM tier means writing concrete new
  actions and wording, which needs judgement. It follows the same `invoke_structured` pattern as
  `build_roadmap` (its own prompt in `agent/prompts/recheck.py`), reusing the existing `Roadmap`
  schema rather than inventing a new one, with the verdict and prior roadmap as context.

### 3.3 Routing on verdict

```
compare_progress ──(improving | static)──▶ revise_roadmap ──▶ persist
                 ──(worsening | new_problem)──▶ enrich ──▶ diagnose ──▶ check_contagion ──▶ build_roadmap ──▶ persist
```

The second branch reuses `enrich`, `diagnose`, `check_contagion`, and `build_roadmap` completely
unmodified — this is the concrete payoff of putting re-check in the same graph.

### 3.4 Persistence

Every re-check inserts a **new `diagnoses` row**, regardless of verdict. For `improving`/`static`,
`revise_roadmap` assigns the prior differential straight into `state.differential` — the same field
every diagnosis run already populates, just with a copied value instead of a fresh `diagnose` call —
so `persist` needs no special case and `differential_json` is never left null. This is a single
population of an existing per-run field, not additional state: it doesn't reintroduce what `P2-3`
avoids, which is holding the *prior* differential alongside the new one for the whole run purely for
`compare_progress`'s comparison. That comparison happens once, off a value read live and never
assigned to state; only the (unchanged, no larger than usual) final answer is written down. New
`roadmap_steps` rows link to this new `diagnosis_id`.

---

## 4. Plant profiles UI

- **`ui/pages/my_plants.py`** — grid of plant cards (photo, name, health badge derived from the
  latest diagnosis's `primary_candidate`/`severity`, a count of pending roadmap steps), plus an
  "add plant" tile that starts a fresh diagnosis. A care queue lists steps due, across all plants.
- **`ui/pages/plant_detail.py`** — reached from the grid. Shows the observation/diagnosis timeline,
  the current roadmap as a *tickable* checklist (distinct from `ui/components/roadmap.py`'s
  read-only render used on the diagnosis result page — ticking calls
  `RoadmapRepository.mark`, now with the `M10` fix), the feedback prompt, a **Re-check** button
  (calls `diagnosis_service.start_recheck`), and a link into chat.
- **New service:** `services/plant_service.py` — `list_plants`, `get_plant_detail` (aggregating
  observations, diagnoses, and roadmap steps for the timeline), `mark_roadmap_step`,
  `submit_feedback`.
- **Feedback trigger:** the prompt appears once the diagnosis's roadmap has **at least one step
  marked done** — not on a fixed delay, not always-on. Asking before anything has been tried
  produces uninformative "too early" answers by construction.

---

## 5. The chat agent

- **`agent/chat_agent.py`** — `create_react_agent`, scoped to one plant via a system prompt that
  injects the plant's record: species, latest diagnosis, roadmap status.
- **Reused tools:** `get_local_weather`, `web_search_plant_info`, `lookup_plant_care_profile`,
  `search_plant_knowledge` — the same underlying functions the pipeline calls as plain `Deps`
  callables, wrapped as LangChain `Tool` objects for the ReAct loop. Two calling conventions over
  one function is a deliberate, noted trade-off, not an oversight.
- **`get_plant_journal`** — read-only, aggregating `observations`/`diagnoses`/`roadmap_steps` into a
  rendered timeline. No new table, no `save_journal_note` (see §1 — nothing yet needs an arbitrary
  per-plant note store beyond what a diagnosis's structured record already carries).
- **Escalation is real, not a suggestion.** A tool the agent can call that actually starts a new
  diagnosis run via `diagnosis_service` when the user describes a materially new symptom, handing
  control back to the UI to collect photos and continue the wizard — matching `PLAN.md` §8's stated
  behaviour rather than softening it into a hyperlink.
- **Persistence:** `MessageRepository` backs the visible transcript (one row per turn). The ReAct
  loop's own scratch state uses a separate checkpointer thread, keyed `chat:{plant_id}`, distinct
  from any diagnosis thread for the same plant.
- **`ui/pages/chat.py`** — scoped to the currently selected plant, message history rendered with
  tool calls shown collapsibly (`PLAN.md` §12).

---

## 6. Testing

Follows the existing convention (`PLAN.md` §19, code tour §5): fakes for chat models, no live LLM
calls by default, assertions on structure and control flow rather than generated prose.

- **New graph tests:** the router sends a re-check straight to `compare_progress`, skipping
  `identify_plant`; each verdict routes to the correct branch; a `worsening`/`new_problem` verdict
  really does reach `diagnose` again; `improving`/`static` never does.
- **New fixture:** `sample_plant` — a persisted plant with one prior diagnosis and a partially
  completed roadmap, the standard re-check starting point. Phase 1 never needed this; it's the one
  fixture gap this phase has to fill.
- **`AppTest` smoke coverage** for `my_plants.py`, `plant_detail.py`, and `chat.py`, at the same
  shallow level Phase 1 used for `diagnose.py` — renders without exception, primary widgets present,
  service-layer errors surface as messages rather than tracebacks.
- **Repository tests** for `FeedbackRepository`, `MessageRepository`, and the `M10` fix
  (`mark()` raises on an unknown `step_id`).

---

## 7. Decisions log

| # | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| P2-1 | One combined spec/plan for all four features | Separate spec per feature | They share the same repositories and the same Plant detail page; splitting would fragment closely related work |
| P2-2 | Re-check is one unified `StateGraph`, not a second compiled graph | Separate `recheck_graph.py` reusing node functions; separate graph invoking the original as a subroutine | Only the unified-graph approach lets a `worsening`/`new_problem` verdict rejoin the existing `enrich→diagnose→check_contagion→build_roadmap` chain unmodified, which is what "full re-diagnosis" in `PLAN.md` §7 actually requires |
| P2-3 | `compare_progress` reads prior diagnosis/roadmap live via repositories, not through graph state | Thread `prior_diagnosis` through `DiagnosisState` as `PLAN.md` §6.2 sketches | Avoids adding a second full differential to the state LangGraph re-checkpoints every superstep, which would compound `M15` rather than merely inherit it |
| P2-4 | Every re-check inserts a new `diagnoses` row, even `improving`/`static` | Only `worsening`/`new_problem` get a new row; `improving`/`static` just touch `roadmap_steps` | `differential_json` is `NOT NULL`; forward-carrying the prior differential keeps one-row-per-observation simple and gives every re-check a full timeline entry |
| P2-5 | `get_plant_journal` is read-only; no `save_journal_note`, no new table | Add a `plant_notes` table; repurpose `messages` for notes | Nothing in scope yet needs an arbitrary note store beyond the structured record a diagnosis already produces |
| P2-6 | `create_care_schedule` dropped from this phase | Make `roadmap_steps.diagnosis_id` nullable; attach ad-hoc steps to the latest diagnosis | No schema support for a diagnosis-less step without a migration; not essential to any of the four in-scope features |
| P2-7 | Chat's escalation tool actually invokes `diagnosis_service` | Chat suggests, user starts a new diagnosis manually; escalation deferred entirely | Matches `PLAN.md` §8's stated behaviour; a genuine agentic decision point rather than a scripted suggestion |
| P2-8 | Learned user profile (C16) deferred to its own pass after this phase | Include a minimal version now (extraction + prompt injection) | Explicitly cuttable per `PLAN.md` §21, and cross-cutting rather than self-contained — cleaner once the four features here are stable. Not abandoned: flagged as a real near-term priority |
| P2-9 | `M10` and `U7` fixed as part of this phase; `M15` carried further | Fix all three; fix none | `M10`/`U7` sit directly in code paths this phase newly exercises (a UI button on `mark()`, a shared reject/retake path); `M15`'s fix is larger and orthogonal to the four features in scope |

---

## 8. Open follow-ups (not blocking this phase)

- Learned user profile (`P2-8`) — the next planning conversation after this phase ships.
- `M15` (checkpoint DB growth) — still carried; re-check makes the underlying compounding worse in
  absolute terms (more pipeline runs per plant) even though `P2-3` avoids adding to *what* gets
  checkpointed per run.
- `create_care_schedule` — revisit if ad-hoc, diagnosis-less scheduling becomes a real ask.
