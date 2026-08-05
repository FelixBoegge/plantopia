# Plantopia — Design Document

An AI plant-health agent that diagnoses ailing plants from photographs, prescribes a dated
treatment roadmap, and follows up over time to judge whether its own treatment worked.

**Status:** design approved, implementation plan not yet written.
**Sprint 3 project brief:** [`135.md`](135.md)

---

## Table of contents

- [1. Problem definition](#1-problem-definition)
- [2. Target users](#2-target-users)
- [3. Why this needs an agent](#3-why-this-needs-an-agent)
- [4. Feature scope](#4-feature-scope)
- [5. Architecture](#5-architecture)
- [6. The diagnosis graph](#6-the-diagnosis-graph)
- [7. The re-check graph (hero feature)](#7-the-re-check-graph-hero-feature)
- [8. The chat agent](#8-the-chat-agent)
- [9. Function tools](#9-function-tools)
- [10. Knowledge base](#10-knowledge-base)
- [11. Data model and memory](#11-data-model-and-memory)
- [12. User interface](#12-user-interface)
- [13. Security and safety](#13-security-and-safety)
- [14. Error handling and edge cases](#14-error-handling-and-edge-cases)
- [15. Observability and cost](#15-observability-and-cost)
- [16. Evaluation](#16-evaluation)
- [17. Project structure](#17-project-structure)
- [18. Stack and tooling](#18-stack-and-tooling)
- [19. Brief requirement traceability](#19-brief-requirement-traceability)
- [20. Effort estimate and descope order](#20-effort-estimate-and-descope-order)
- [21. Risks](#21-risks)
- [22. Decisions log](#22-decisions-log)

---

## 1. Problem definition

Plant symptoms are **many-to-one ambiguous**. A single visible symptom maps to many possible
causes. Yellowing leaves, taken alone, are consistent with all of the following:

- overwatering
- underwatering
- nitrogen deficiency
- insufficient light
- root rot
- spider mite infestation
- natural senescence of lower leaves
- transplant shock

Existing consumer plant apps perform one-shot image classification. They ask nothing, explain
nothing, cite nothing, and never follow up. The result is confident advice that is frequently
wrong, with no signal to the user about when to distrust it. Acting on a wrong diagnosis is
actively harmful: watering a plant with root rot accelerates its death.

**The decisive observation:** a correct diagnosis depends on information that is *not present in
the photograph* — watering cadence, pot drainage, daily light hours, time since last repotting,
indoor vs. outdoor, and recent local weather. A system that only looks at pixels is structurally
incapable of resolving the ambiguity.

Plantopia therefore **asks before it answers**, the way a clinician takes a history before
diagnosing.

---

## 2. Target users

**Primary:** houseplant owners and hobby gardeners who can see that something is wrong but cannot
name it. Today they guess, or post a photo to a forum and wait a day for a contradictory answer.

**Secondary:** balcony, allotment and small-scale urban growers, for whom weather history is a
material diagnostic input.

**Explicitly not the target:** commercial horticulture and agronomy. Those users need
species-specific pathology depth, regulatory pesticide guidance and field-scale scouting that
this project does not attempt.

---

## 3. Why this needs an agent

The brief grades understanding of when prompt engineering, RAG and agents are each appropriate.
Plantopia's design answers that question concretely:

| Approach | Why it is insufficient alone |
|---|---|
| **Prompt engineering only** | A single vision prompt cannot obtain the off-image facts required to disambiguate. It also cannot cite a source, so its treatment advice is unfalsifiable model recall. |
| **RAG only** | Retrieval grounds the pathology knowledge but cannot decide *which* query to issue — the query itself depends on symptoms extracted from the image and on the user's answers. Retrieval also cannot conduct a follow-up two weeks later. |
| **Agent** | Required because the task is genuinely multi-step with **data-dependent control flow**: identify species → extract symptoms → *decide which questions are worth asking* → pause for the human → retrieve → decide whether retrieval was sufficient → possibly escalate to web search → diagnose → plan → persist → resume weeks later with memory of what was prescribed. |

Three properties make the agent framing non-decorative:

1. **A mandatory human-in-the-loop pause.** The graph cannot proceed to diagnosis without user
   answers. This is a `interrupt()`, not a form.
2. **Conditional tool use.** Weather is fetched only for outdoor plants. Web search fires only
   when local retrieval is weak. The agent decides.
3. **State that outlives the session.** The re-check flow reads a diagnosis made weeks earlier and
   evaluates its own prior recommendation.

---

## 4. Feature scope

### 4.1 Core

Everything here is planned for the initial release. If time runs short, §20 defines the exact
order in which these are cut and which five are protected unconditionally.

| # | Feature | Notes |
|---|---|---|
| C1 | **Multi-photo intake** | Whole plant + close-up of affected area + soil surface. Symptoms are ambiguous from one angle. |
| C2 | **Photo quality gate** | Rejects blurry, dark or over-cropped images and asks for a better one. |
| C3 | **Species identification** | Vision-based, with confidence. User can correct it — a second HITL point. |
| C4 | **Structured symptom extraction** | Leaf colour pattern and its location on the plant, spotting, webbing, wilting, leaf drop, soil surface condition, new-growth appearance. |
| C5 | **Dynamic clarifying questions** | 2–4 highest-value questions chosen per case, not a fixed questionnaire. Delivered via LangGraph `interrupt()`. |
| C6 | **Differential diagnosis** | 2–3 ranked candidates. Each carries probability, supporting evidence, contradicting evidence, **a distinguishing test the user can perform**, severity/urgency, and contagion risk. Never a single bare answer. |
| C7 | **Grounded reasoning** | Diagnoses cite retrieved knowledge-base passages, surfaced in the UI. |
| C8 | **Treatment roadmap** | Structured dated steps, not prose. Each step: action, when, why, how to tell it worked, expected time to visible improvement. Rendered as a tickable checklist. |
| C9 | **Plant profiles** | Named plants with photo, species, location, and full history. |
| C10 | **Progress re-check** | Upload a new photo of a known plant; the agent compares against the stored prior diagnosis, returns a verdict (*improving / static / worsening / new problem*) and revises the roadmap. **The hero feature.** |
| C11 | **Treatment-outcome feedback** | User rates whether a treatment helped; this is stored and fed into later reasoning. |
| C12 | **Scoped chat** | ReAct agent conversation about a specific plant, sharing tools and reading that plant's record. Can escalate to a full re-diagnosis. |
| C13 | **Contagion triage** | Checks the journal for other plants and advises quarantine when the diagnosed pathogen is transmissible. |
| C14 | **Severity flag** | *Act today* vs. *act this week* vs. *monitor*. |
| C15 | **Token and cost display** | Per-diagnosis and per-session, surfaced in the UI and stored with each diagnosis. |
| C16 | **Learned user profile** | Extracted durable facts (location, tendency to overwater, prior infestations) injected into system prompts. |

### 4.2 Stretch (build if time allows)

| # | Feature | Notes |
|---|---|---|
| S1 | **Developer settings sidebar** | Model choice, temperature, system-prompt inspection, and per-tool enable/disable toggles — kept strictly separate from the end-user flow, per the brief's usability note. |
| S2 | **External species cross-check** | A second opinion on identification from a species-ID API, reconciled against the vision model's answer. |
| S3 | **Multi-provider model support** | Swap the OpenAI model for another provider behind the existing LLM factory. |

### 4.3 Deliberately out of scope

Recorded here because knowing what *not* to build is part of the reflection criteria.

- **User accounts and authentication.** Single local user. Auth adds no learning value here and
  costs UI surface.
- **Product and shopping recommendations.** Turns a diagnostic tool into an affiliate funnel and
  creates a bias toward chemical interventions.
- **Push notifications and reminders.** Requires a scheduler and a delivery channel; the care
  queue on the home page covers the need adequately.
- **Community features.** Out of scope for a single-user local app.
- **Computer-vision severity scoring over time** (measuring lesion area growth across photos).
  Interesting, but a separate project.
- **Mobile app.** Streamlit is the specified front end.

---

## 5. Architecture

Monolithic Python application, layered, with a single hard rule: **the Streamlit layer never calls
an LLM or touches the database directly.** It calls a service layer. This keeps the agent testable
without a browser and keeps pages small.

```
┌─────────────────────────────────────────────────────────────┐
│  ui/            Streamlit pages — rendering and input only  │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  services/      orchestration boundary the UI talks to      │
│                 diagnosis_service, plant_service,           │
│                 chat_service                                │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
┌──▼───────┐┌─▼────────┐┌▼─────────┐┌▼────────┐┌▼─────────────┐
│ agent/   ││ tools/   ││knowledge/││ data/   ││ core/        │
│ LangGraph││ 7 func   ││ corpus → ││ SQLite  ││ config, llm  │
│ graphs,  ││ tools    ││ Chroma → ││ repos   ││ factory,     │
│ state,   ││          ││ retriever││ (long-  ││ cost, guards,│
│ prompts  ││          ││          ││  term   ││ logging      │
│          ││          ││          ││  memory)││              │
└──────────┘└──────────┘└──────────┘└─────────┘└──────────────┘
```

### 5.1 Why hybrid pipeline + ReAct

Two agent architectures coexist deliberately:

- The **diagnosis pipeline** is an explicit LangGraph state machine. Ordering is guaranteed:
  species identification always precedes diagnosis, and the clarifying-question interrupt always
  fires. A free-form agent asked to do this reliably will sometimes skip the questions or diagnose
  before identifying the plant, which would make the human-in-the-loop requirement unreliable.
- The **chat agent** is a ReAct loop. Follow-up conversation has no predictable shape, so
  imposing a graph on it would be worse than letting the model choose its own tool sequence.

The trade-off is stated plainly: the pipeline buys reliability at the cost of flexibility; ReAct
the reverse. Having both in one codebase is also the concrete basis for the architectural
comparison the brief asks for.

---

## 6. The diagnosis graph

LangGraph `StateGraph`, persisted with a SQLite checkpointer so a session survives page reloads
and abandoned interrupts.

```
  photos
    │
    ▼
┌─────────────┐  not a plant   ┌──────────────────┐
│ guard_input ├───────────────▶│ reject + explain │
└──────┬──────┘                └──────────────────┘
       │ ok
       ▼
┌───────────────┐  too poor     ┌─────────────────────────┐
│ quality_check ├──────────────▶│ ask for a better photo  │
└──────┬────────┘               └─────────────────────────┘
       │ usable
       ▼
┌────────────────┐
│ identify_plant │  species + confidence; user may correct
└──────┬─────────┘
       ▼
┌──────────────────┐
│ assess_symptoms  │  structured symptom extraction
└──────┬───────────┘
       ▼
┌──────────────────┐
│ gather_context   │ ══ interrupt() ══▶  2–4 questions chosen
└──────┬───────────┘      resume        for THIS case
       ▼
┌──────────────────┐
│ enrich           │ ── search_plant_knowledge  (multi-query)
│                  │ ── get_local_weather       (outdoor only)
│                  │ ── lookup_plant_care_profile
│                  │ ── web_search_plant_info   (only if retrieval weak)
└──────┬───────────┘
       ▼
┌────────────┐    ┌──────────────────┐    ┌───────────────┐    ┌─────────┐
│ diagnose   │───▶│ check_contagion  │───▶│ build_roadmap │───▶│ persist │
└────────────┘    └──────────────────┘    └───────────────┘    └─────────┘
```

### 6.1 Node responsibilities

| Node | Input | Output | Notes |
|---|---|---|---|
| `guard_input` | images | pass/reject + reason | Cheap vision check: is this a plant? Blocks the "upload a person, receive medical advice" path. |
| `quality_check` | images | usable/retake + guidance | Blur, exposure, framing. Asking for a better photo is cheaper than diagnosing a bad one. |
| `identify_plant` | images | species, genus, confidence | User-correctable. Low confidence is carried forward, not hidden. |
| `assess_symptoms` | images | structured `SymptomSet` | Colour pattern **and its position on the plant** (tip vs. margin vs. interveinal vs. lower leaves) — position is the single most diagnostic feature and a plain classifier throws it away. |
| `gather_context` | symptoms, species | questions → **interrupt** → answers | Questions selected by expected diagnostic value for this symptom set, capped at 4 to avoid interrogating the user. |
| `enrich` | all of the above | retrieved passages, weather, care baseline | Conditional tool use. Records which tools fired and why, for the trace. |
| `diagnose` | everything | `Differential` (Pydantic) | 2–3 ranked candidates with evidence for and against. Structured output, validated. |
| `check_contagion` | primary candidate, journal | quarantine advice | Queries other plants in the journal. Uses long-term memory in a way the user can feel. |
| `build_roadmap` | diagnosis, species | dated `RoadmapStep[]` | Ordered by integrated-pest-management escalation (see §13.5). |
| `persist` | all | DB writes | Single transaction. |

### 6.2 Core state

```
DiagnosisState:
  plant_id            int | None        # None for a first-time diagnosis
  images              ImageRef[]
  species             SpeciesGuess | None
  symptoms            SymptomSet | None
  questions           Question[]
  answers             dict[str, str]
  retrieved           Passage[]
  weather             WeatherSummary | None
  care_baseline       CareProfile | None
  differential        Differential | None
  contagion           ContagionAssessment | None
  roadmap             RoadmapStep[]
  prior_diagnosis     Diagnosis | None   # populated on re-check
  tool_calls          ToolCallRecord[]   # for trace + cost display
  usage               TokenUsage
  errors              str[]
```

---

## 7. The re-check graph (hero feature)

A second entry point into the same graph, with the prior diagnosis and roadmap-step completion
history injected into state.

```
new photo + plant_id
    │
    ▼
guard_input ─▶ quality_check ─▶ assess_symptoms      (species already known — skipped)
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │ compare_progress       │  new symptoms vs. prior symptoms
                        │                        │  + which roadmap steps were done
                        └───────────┬────────────┘
                                    ▼
                        verdict: improving | static | worsening | new problem
                                    │
                        ┌───────────▼────────────┐
                        │ revise_roadmap         │
                        │  improving → continue, taper
                        │  static    → escalate one IPM tier
                        │  worsening → re-open differential, consider 2nd candidate
                        │  new       → full re-diagnosis
                        └───────────┬────────────┘
                                    ▼
                                 persist
```

This is what distinguishes Plantopia from a classifier: **the agent evaluates its own prior
recommendation.** A *worsening* verdict after full compliance is strong evidence the primary
candidate was wrong, and the agent promotes the runner-up in the differential rather than
insisting on its first answer.

---

## 8. The chat agent

A `create_react_agent` ReAct loop, scoped to the currently selected plant.

- Shares all seven tools with the pipeline.
- Reads the selected plant's record: species, diagnosis history, roadmap status, feedback.
- Short-term memory is the LangGraph checkpointer, one thread per plant.
- Long-term memory is reached through `get_plant_journal` / `save_journal_note`.
- May escalate: if the user describes a materially new symptom, the agent invokes the diagnosis
  pipeline rather than free-associating an answer.
- Personality: knowledgeable, plain-spoken, calibrated. Never falsely reassuring, never
  catastrophising.

---

## 9. Function tools

Seven tools. Each is a plain Python function with a typed signature and a docstring the model
sees; none of them wrap another LLM call except where noted.

| Tool | Signature (shape) | Purpose | Failure mode |
|---|---|---|---|
| `search_plant_knowledge` | `(query: str, k: int) -> Passage[]` | Chroma similarity search over the curated corpus. Primary grounding. | Empty result → caller escalates. |
| `web_search_plant_info` | `(query: str) -> Passage[]` | Tavily. **Escalation only**, gated on weak retrieval or unknown species. | API error → degrade, do not fail the diagnosis. |
| `get_local_weather` | `(location: str, days_back: int) -> WeatherSummary` | Open-Meteo historical archive. Free, no API key. A recent frost, heatwave or three weeks of rain frequently *is* the diagnosis. | Unresolvable location → omit weather, note the gap. |
| `lookup_plant_care_profile` | `(species: str) -> CareProfile` | Baseline light/water/temperature/humidity requirements. Grounds "is this normal *for a fern*". | Unknown species → return `None`, widen the differential. |
| `get_plant_journal` | `(plant_id: int) -> JournalEntry[]` | Long-term memory read. | — |
| `save_journal_note` | `(plant_id: int, note: str) -> None` | Long-term memory write. | — |
| `create_care_schedule` | `(plant_id: int, steps: RoadmapStep[]) -> None` | Materialises the roadmap into dated, tickable tasks. | Transactional. |

**Escalation gate for web search.** Fires when *either* the best retrieval similarity falls below
a configured threshold *or* species identification confidence is low. This gate is the concrete
answer to "when RAG, when search": the curated corpus is authoritative and reproducible, so it is
consulted first; the web is current but unvetted, so it is a fallback whose provenance is shown to
the user.

---

## 10. Knowledge base

### 10.1 Corpus

40–60 hand-authored markdown documents, one per disorder, covering the disorders that actually
account for most houseplant and small-garden failures:

- **Water and root:** overwatering, underwatering, root rot, poor drainage, transplant shock
- **Nutrient:** nitrogen, phosphorus, potassium, iron, magnesium, calcium deficiency; fertiliser burn
- **Light and environment:** insufficient light, sunscald, low humidity, cold draught, frost damage, heat stress
- **Pests:** spider mites, thrips, aphids, mealybugs, scale insects, fungus gnats, whitefly
- **Disease:** powdery mildew, botrytis, leaf spot (bacterial and fungal), rust, anthracnose
- **Other:** salt build-up, pot-bound roots, natural senescence, chemical/cleaning-product damage

### 10.2 Document schema

Every document uses the same headed structure, because that structure is what makes differential
reasoning work:

```markdown
---
id: root-rot
category: water-and-root
transmissible: false
severity: high
---

# Root rot

## Symptoms
## Where on the plant symptoms appear
## Look-alikes and how to tell them apart      <- powers the differential
## Confirming test the user can perform        <- powers the distinguishing test
## Treatment, least-invasive first             <- powers the roadmap
## Expected time to visible improvement
## Prognosis and when to give up
```

The `Look-alikes` and `Confirming test` sections are the reason a curated corpus beats scraped
PDFs here: scraped documents describe a disorder in isolation, but diagnosis is a *discrimination*
task, and the discriminating information has to be written down deliberately.

### 10.3 Indexing

Chunked per section (headings preserved as metadata), embedded, stored in a local Chroma
collection. Metadata filters on category and `transmissible` support the contagion check.
Retrieval is multi-query: one query per extracted symptom plus one combined query, then
deduplicated and reranked.

---

## 11. Data model and memory

### 11.1 Two memory tiers

**Short-term** — LangGraph SQLite checkpointer. One thread per plant. Holds graph state across
the clarifying-question interrupt and across page reloads. Disposable.

**Long-term** — the application's own SQLite tables. This is the substantive memory: it is what
makes the re-check flow possible and what the contagion check queries.

### 11.2 Schema

```
plants
  id, name, species, species_confidence, location_kind (indoor|outdoor),
  location_text, acquired_at, photo_ref, created_at

observations
  id, plant_id, kind (initial|recheck), photo_refs, user_notes, created_at

diagnoses
  id, observation_id, plant_id, differential_json, primary_candidate,
  primary_confidence, severity, contagion_json, retrieved_refs_json,
  model, token_usage_json, cost_usd, created_at

roadmap_steps
  id, diagnosis_id, plant_id, ordinal, action, rationale,
  success_signal, due_date, status (pending|done|skipped), completed_at

feedback
  id, diagnosis_id, rating, did_it_help (yes|no|unclear|too_early),
  free_text, created_at

user_profile
  id, fact, source (inferred|stated), confidence, first_seen, last_confirmed

messages
  id, plant_id, role, content, tool_calls_json, created_at
```

### 11.3 The learned user profile

After a session, durable facts are extracted and stored: *"user is in Berlin"*, *"user tends to
overwater"*, *"the Monstera had spider mites in March"*. These are injected into system prompts on
later runs, so the agent's priors shift with evidence. Facts carry a confidence and a
`last_confirmed` timestamp, and stale or contradicted facts are re-confirmed rather than trusted
indefinitely.

This is a modest but real implementation of an agent that improves from feedback: repeated
overwatering diagnoses raise the prior on water-related causes for that user.

---

## 12. User interface

Streamlit multipage app via `st.navigation`.

```
┌─ 🌿 Plantopia ───────────────────────────────────┐
│ My Plants │ Diagnose │ Chat │ Evaluation │ ⚙ Dev │
├──────────────────────────────────────────────────┤
│  ┌───────┐  ┌───────┐  ┌───────┐                 │
│  │ 📷    │  │ 📷    │  │   +   │                 │
│  │ Ficus │  │ Basil │  │ add   │                 │
│  │ 🟡 mon │  │ 🔴 act │  │ plant │                 │
│  └───────┘  └───────┘  └───────┘                 │
│                                                  │
│  Needs attention: Basil — step 2 due today       │
└──────────────────────────────────────────────────┘
```

| Page | Contents |
|---|---|
| **My Plants** | Plant grid with health badge (🔴 act today / 🟡 monitor / 🟢 healthy), plus a care queue of steps due. The home surface. |
| **Diagnose** | The intake wizard: upload → quality gate → species confirmation → clarifying questions → differential → roadmap. Progress is visible; each agent step is named as it runs. |
| **Plant detail** | Timeline of observations and diagnoses, current roadmap as a tickable checklist, feedback prompt, and a *Re-check* button. Reached from the grid. |
| **Chat** | Conversation scoped to the selected plant. Tool calls shown collapsibly, so the user can see *why* an answer was given. |
| **Evaluation** | Renders the Ragas/DeepEval scores from the golden-set run. |
| **⚙ Dev** *(stretch)* | Model, temperature, system prompts, per-tool toggles, raw trace. Kept out of the user path. |

Design principles: the differential is rendered as ranked cards with confidence bars, not prose;
every diagnosis shows its sources; the distinguishing test is a call to action, not a footnote;
cost is visible but unobtrusive.

---

## 13. Security and safety

The domain is advice-giving and adjacent to harm — bad advice kills plants — so guards are part of
the design, not an afterthought.

### 13.1 Non-plant image rejection

`guard_input` classifies whether the upload is plant material before anything else runs. This
closes the obvious misuse path of uploading a photo of a person or a skin condition and receiving
diagnostic-sounding advice from a system with no medical competence.

### 13.2 Untrusted-data handling

Text visible inside uploaded images, and any content returned by web search, is treated as **data,
never as instructions**. System prompts state an explicit instruction hierarchy, retrieved content
is delimited and labelled as untrusted, and the agent is instructed to report rather than obey any
instruction found in retrieved or image-embedded text.

### 13.3 Scope guard

The chat agent declines human and animal medical questions and redirects. It does **not** refuse
questions about controlled or restricted plant species — cultivation legality varies by
jurisdiction and a plant-health question is a plant-health question. The guard is about staying
within botanical competence, not about policing which plants the user grows.

### 13.4 Calibrated uncertainty

Confidence is always displayed. Below a configured threshold the agent says it cannot tell, names
the specific evidence that would resolve the ambiguity, and suggests a local nursery or extension
service. A wrong confident answer is worse than an honest refusal, because the user acts on it.

### 13.5 Integrated pest management ordering

Treatment recommendations escalate in the order real horticultural practice uses:

1. **Cultural** — adjust watering, light, drainage, airflow, spacing
2. **Mechanical** — prune affected tissue, wipe or rinse pests off, sticky traps
3. **Biological** — beneficial insects, microbial controls
4. **Chemical** — least-toxic option only, and never a specific dose of a restricted product;
   the user is directed to the product label

This is both a safety property and a signal of genuine domain competence.

### 13.6 Input and operational hygiene

- Upload MIME and magic-byte validation; images re-encoded before use; size cap
- Per-session request cap to bound cost
- API keys from environment only; `.env` git-ignored; no secrets in the repo or in traces
- SQL through parameterised queries only
- Uploaded images stored outside the served static path, referenced by opaque id

---

## 14. Error handling and edge cases

| Scenario | Handling |
|---|---|
| Vision API error or timeout | Retry with exponential backoff; on exhaustion, degrade to a text-only questionnaire diagnosis with confidence reduced and the degradation stated to the user |
| Structured output fails validation | Pydantic validation, then one repair retry with the validation error fed back; then fail cleanly |
| Retrieval returns nothing relevant | Escalate to web search; if still nothing, return an honest "I cannot identify this" rather than a guess |
| Web search unavailable | Proceed on curated corpus alone, flag reduced coverage |
| Unresolvable location for weather | Omit the weather input, note the missing evidence in the diagnosis |
| Unknown species | Diagnose on generic plant physiology, widen the differential, lower confidence |
| Blurry / dark / over-cropped photo | `quality_check` requests a retake with specific guidance |
| User abandons mid-interrupt | Checkpointer resumes the run on return; unfinished runs surfaced on the home page |
| Multiple plants visible in one photo | Ask which one to diagnose — do not silently pick |
| Healthy plant submitted | Say so. Do not manufacture a problem to be useful. |
| Two concurrent problems (pests *and* deficiency) | The differential is not mutually exclusive; the roadmap sequences both, most urgent first |
| Re-check with no roadmap steps completed | Verdict accounts for non-compliance rather than concluding the treatment failed |
| SQLite write failure | Single transaction per persist; never an orphaned diagnosis |
| Duplicate plant names | Allowed, disambiguated by id in the UI |

---

## 15. Observability and cost

**LangSmith** tracing, chosen over Langfuse because it is LangChain-native — tracing is largely
environment configuration rather than callback wiring. Every graph node, tool call, retrieval and
model call appears in the trace, which matters a great deal when debugging a ten-node graph with
an interrupt in the middle.

**Cost tracking** via a token-usage callback: per-node usage aggregated per run, converted to a
cost figure from a configured price table, displayed in the UI and stored on the `diagnoses` row.
This makes the cost of a diagnosis a visible, discussable engineering property rather than an
invisible bill.

---

## 16. Evaluation

A golden set of 25–30 cases, each comprising: photographs, pre-written answers to the clarifying
questions, and a ground-truth primary cause. Images sourced from a public labelled leaf-disease
dataset (PlantVillage-style), with licence checked before inclusion, supplemented by
hand-annotated cases for disorders such disease-focused datasets omit — notably watering and light
problems.

| Metric | What it tells us |
|---|---|
| Context precision / recall | Is retrieval surfacing the right knowledge-base passages? |
| Faithfulness | Does the diagnosis actually follow from the retrieved passages, or is the model free-associating? |
| Answer relevancy | Does the response address the user's situation? |
| **Top-1 diagnostic accuracy** | The metric that matters: was the primary candidate correct? |
| **Top-3 diagnostic accuracy** | Was the correct cause anywhere in the differential? A high top-3 with a mediocre top-1 tells us ranking, not retrieval, is the weak point. |

Reported as a committed markdown artefact plus the in-app **Evaluation** page. The report includes
per-category breakdowns, since failure is likely to be concentrated (pests are visually distinctive;
nutrient deficiencies are notoriously confusable with each other).

---

## 17. Project structure

```
plantopia/
├── app.py                          # Streamlit entry point, st.navigation
├── ui/
│   ├── pages/
│   │   ├── my_plants.py
│   │   ├── diagnose.py
│   │   ├── plant_detail.py
│   │   ├── chat.py
│   │   ├── evaluation.py
│   │   └── dev_settings.py         # stretch
│   └── components/                 # differential cards, roadmap checklist,
│                                   # timeline, cost badge, source panel
├── services/
│   ├── diagnosis_service.py        # the only thing the UI calls to diagnose
│   ├── plant_service.py
│   └── chat_service.py
├── agent/
│   ├── state.py                    # DiagnosisState, ChatState
│   ├── schemas.py                  # Pydantic: SpeciesGuess, SymptomSet,
│   │                               # Differential, RoadmapStep, ...
│   ├── diagnosis_graph.py
│   ├── recheck_graph.py
│   ├── chat_agent.py
│   ├── nodes/                      # one module per node
│   └── prompts/                    # versioned prompt templates
├── tools/                          # one module per tool + registry
├── knowledge/
│   ├── corpus/                     # 40–60 markdown documents
│   ├── ingest.py
│   └── retriever.py
├── data/
│   ├── schema.sql
│   ├── db.py
│   └── repositories/
├── core/
│   ├── config.py                   # pydantic-settings
│   ├── llm.py                      # model factory
│   ├── cost.py
│   ├── guards.py
│   └── logging.py
├── eval/
│   ├── golden_set/
│   ├── run_eval.py
│   └── REPORT.md
├── tests/
├── docs/
├── pyproject.toml
├── .env.example
└── README.md
```

One responsibility per module; nodes and tools are individually testable without Streamlit.

---

## 18. Stack and tooling

| Concern | Choice |
|---|---|
| Package management | **uv**, Python 3.12 |
| Front end | Streamlit (multipage via `st.navigation`) |
| Agent framework | LangGraph + LangChain |
| Model provider | OpenAI, vision-capable model; exact id pinned in config at implementation time |
| Structured output | Pydantic v2 |
| Vector store | Chroma (local, persistent) |
| Relational store | SQLite (stdlib `sqlite3` via a thin repository layer) |
| Checkpointer | LangGraph SQLite saver |
| Web search | Tavily |
| Weather | Open-Meteo historical archive (no key required) |
| Observability | LangSmith |
| Evaluation | **Ragas** — the stronger fit for RAG-specific metrics (context precision/recall, faithfulness) |
| Images | Pillow |
| HTTP | httpx |
| Config | pydantic-settings, `.env` |
| Tests | pytest |
| Lint / format | ruff |

---

## 19. Brief requirement traceability

### Required tasks

| Requirement | Where it is satisfied |
|---|---|
| Clear agent purpose | §1, §2 |
| Why the agent is useful | §1, §3 |
| Target users identified | §2 |
| Core functionality implemented | §4.1, §6, §7, §8 |
| Necessary user interactions | HITL interrupt (§6), species correction, roadmap ticking, feedback, chat |
| User-friendly interface for all functionality | §12 |
| Appropriate tools and libraries | §18 |
| Proper error handling | §14 |
| Handles real-world usage | §13, §14 |
| Documentation with examples and decisions | `README.md`, this document, §22 |

### Optional tasks claimed

| Task | Level | Where |
|---|---|---|
| Agent personality | Easy 2 | §8 |
| Interactive help / guide chatbot | Easy 5 | §8 |
| Token usage and cost display | **Medium 1** | §15, C15 |
| Long-term and short-term memory | **Medium 2** | §11 |
| Function tool calling an external API | **Medium 3** | `get_local_weather`, `web_search_plant_info` (§9) |
| Feedback loop with user ratings | **Medium 5** | C11, `feedback` table (§11.2) |
| Security guard against misuse | **Medium 8** | §13 |
| Agentic RAG | **Hard 1** | §6 `enrich`, §10 |
| LLM observability (LangSmith) | **Hard 2** | §15 |
| AI evaluation report (Ragas/DeepEval) | **Hard 3** | §16 |
| Agent learning from user feedback | **Hard 4** (partial) | §11.3 learned user profile |
| Integration with external data sources | **Hard 5** | §9 weather + web search |

Bonus threshold is 2 medium + 1 hard. The plan claims **five medium and five hard** (Hard 4 partial).

### Optional tasks deliberately not claimed

| Task | Level | Reason |
|---|---|---|
| User-selectable LLM list | Easy 3 | Folded into stretch S3; not core to the problem |
| OpenAI parameter sliders | Easy 4 | Belongs in the developer sidebar (stretch S1) |
| User authentication | Medium 4 | Single-user app by decision (§4.3) |
| Plugin system with tool toggles | Medium 6 | Stretch S1 |
| Multi-model support | Medium 7 | Stretch S3 |

---

## 20. Effort estimate and descope order

The brief estimates 18 hours. This design is larger, by choice — it is intended as a portfolio
piece.

| Workstream | Estimate |
|---|---|
| Project scaffold, config, uv setup, DB schema and repositories | 4 h |
| Knowledge-base authoring (40–60 structured documents) | 4 h |
| Ingestion and retrieval, multi-query, reranking | 2 h |
| Diagnosis graph: nodes, schemas, prompts, interrupt | 8 h |
| Re-check graph and progress comparison | 4 h |
| The seven tools | 3 h |
| ReAct chat agent | 3 h |
| Streamlit UI, all pages and components | 7 h |
| Guards and error handling | 3 h |
| LangSmith and cost tracking | 2 h |
| Evaluation: golden set, harness, report | 5 h |
| Tests | 3 h |
| Documentation and README | 2 h |
| **Total** | **~50 h** |

**Descope order**, first to go:

1. Evaluation report (§16) — highest cost per unit of user value
2. Web-search escalation (retain the curated corpus)
3. Learned user profile (§11.3)
4. Contagion triage (C13)
5. Photo quality gate (C2)

**Must survive any descope:** the diagnosis pipeline with its interrupt, plant profiles with
long-term memory, the re-check flow, the differential with distinguishing tests, and the chat
agent. Those five *are* the project.

---

## 21. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Overconfident wrong diagnoses** | Users kill plants acting on bad advice | Differential rather than single answer; mandatory confidence display; distinguishing tests; refusal below a confidence threshold; escalation advice |
| Vision model conflates visually similar disorders | Poor top-1 accuracy | Symptom *position* extracted explicitly; look-alike sections in the corpus; the clarifying questions exist precisely to separate look-alikes |
| Knowledge base too thin for unusual species | Irrelevant retrieval | Web-search escalation; generic-physiology fallback; honest uncertainty |
| Scope overrun against the 18 h estimate | Unfinished project | Explicit descope order (§20); core five features protected |
| Cost per diagnosis higher than expected (multi-image vision) | Unpleasant bill | Per-session cap; cost surfaced in the UI; image downscaling before upload |
| Streamlit rerun model fighting a long-running graph with an interrupt | Confusing UX, lost state | Checkpointer-backed state; graph progress rendered from persisted state rather than in-memory session state |
| Golden-set labels not transferable | Misleading evaluation numbers | Licence and label provenance checked; per-category reporting so weak categories are visible rather than averaged away |
| Prompt injection via image text or web content | Agent misbehaviour | Instruction hierarchy; retrieved content labelled untrusted (§13.2) |

---

## 22. Decisions log

| # | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| D1 | Name: **Plantopia** | — | Chosen by the project owner |
| D2 | Persistent plant profiles with progress tracking as the hero feature | Single-session diagnosis tool; persistence without a re-check flow | The follow-up loop is what makes it an agent rather than a classifier, and it is the strongest portfolio differentiator |
| D3 | Hybrid architecture: deterministic diagnosis pipeline + ReAct chat | Single ReAct agent with all tools; supervisor multi-agent | The pipeline guarantees the interrupt fires and that identification precedes diagnosis; ReAct suits unstructured follow-up. Supervisor multi-agent costs 2–3× tokens and latency for no gain here |
| D4 | Curated markdown corpus, with web-search escalation | Ingesting public extension PDFs; live web search only | Diagnosis is a discrimination task; look-alike and confirming-test sections must be authored deliberately. Escalation covers the long tail and yields a clean "when RAG vs. when search" story |
| D5 | LangSmith for observability | Langfuse | LangChain-native; tracing is configuration rather than callback wiring |
| D6 | Ragas/DeepEval evaluation report included | Skipping formal evaluation | Strongest available evidence of quality; first item in the descope order if time runs out |
| D7 | Streamlit multipage | Single chat-first page; dashboard with drill-down modals | The plant timeline and roadmap checklist need real space; small per-page modules keep the code tractable |
| D8 | Single user, no authentication | Auth with per-user data | Adds UI surface and no learning value; the brief does not require it |
| D9 | No refusal on controlled or restricted plant species | Refusing cannabis and similar | Legality is jurisdictional and a plant-health question is a plant-health question. The scope guard exists to keep the agent within botanical competence, not to police the user's garden |
| D10 | Developer settings sidebar kept as a stretch item | Building it as core; cutting it entirely | The brief calls out separating developer settings from the user experience, so it is worth doing — but it is not on the critical path |
| D11 | SQLite for both domain data and checkpointing | Postgres; JSON files | Zero-configuration, single-user, monolithic; keeps the whole app runnable with `uv run` |
| D12 | Treatment recommendations ordered by IPM escalation | Recommending the most effective treatment first | Least-invasive-first is real horticultural practice and materially safer |
