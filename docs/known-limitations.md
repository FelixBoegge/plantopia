# Known limitations and carried work

Every gap this project shipped with, from Phase 1 onward. Each was raised during review,
judged non-blocking, and deliberately carried rather than silently dropped. They are
recorded here so the next person to touch this code — including future me — inherits the
reasoning, not just the code.

Rows are struck through and dated when resolved rather than deleted: what a fix cost, and
which diagnosis of the problem turned out to be wrong, is usually worth more than the fact
that it is closed. The dated sections after the tables are the run-by-run record.

Grouped by whether they can bite a user, a maintainer, or nobody yet.

---

## Can affect a user

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| U1 | **Parts of the pipeline still have not run live.** *Resolved for the main path on 2026-08-10* — see [First live run](#first-live-run). Still unexercised against real APIs: the outdoor/weather branch, web-search escalation (no Tavily key), the healthy-plant branch, and the retake path. | The main path is now verified; the rest degrade rather than crash. | Run a case that triggers each: an outdoor plant with a town, a healthy plant, a deliberately blurry photo. |
| U2 | **~~The multimodal embeddings request shape is unverified.~~** *Resolved 2026-08-10, and the underlying feature is disabled.* The shape was never exercised because no multimodal embedding model is reachable at all: `google/gemini-embedding-2` (the old default) does not exist on OpenRouter, and `gemini-embedding-001`, the only real candidate, is data-policy blocked on restricted keys. `PLANTOPIA_MULTIMODAL_EMBEDDINGS` now defaults to `false`. | The slug came from a docs fetch and was flagged unverified precisely because it might be wrong. It was. | The request shape in `core/embeddings.py` remains unverified and will stay so until a multimodal embedder is reachable — re-check it against OpenRouter's reference at that point, not before. |
| U3 | **Uploads are not re-encoded or downscaled.** Pillow is a dependency but unused; four 8 MB images go to the vision model at full size. | No correctness impact; cost only. | Downscale in `core/images.py:store_upload` before base64 encoding. |
| U4 | **An unanswered boolean question is recorded as "no".** `ui/pages/diagnose.py` conflates "no" with "didn't say". | Only the mandatory drainage question is a choice; boolean questions are model-generated and rare. | Use a tri-state widget or omit unanswered keys from the answers dict. |
| U5 | **The low-confidence banner omits the escalation advice** PLAN §13.4 specifies — it names the distinguishing tests but never suggests a local nursery or extension service. | The substantive half (tests to run) is present. | One sentence in `ui/components/differential.py`. |
| U6 | **`calcium-deficiency` omits blossom-end rot**, the most recognisable calcium symptom in fruiting plants. | The corpus deliberately skews houseplant/ornamental; the document is correct for that scope. | Add a section if the corpus ever grows toward edibles. |
| U7 | **~~Rejected and retake paths do not rotate `thread_id`.~~** *Resolved 2026-08-12 — added `_rotate_thread()` helper called on both rejected and retake branches in ui/pages/diagnose.py.* State from the abandoned attempt stayed in the checkpoint and merged into the retry. **Amended 2026-08-12 (whole-branch review):** the first fix covered only the wizard. The re-check entry point derived its thread id as `recheck-{plant_id}-{latest_diagnosis_id}`, and neither a rejection nor a retake writes a diagnosis — so that id never changed and a second attempt resumed the abandoned run's checkpoint, the same bug class in the other entry point. `ui/pages/plant_detail.py` now appends a `recheck_attempt` counter that `_rotate_recheck_thread()` increments on both branches. | Fixed by rotating thread_id on both paths, in both entry points. | ✓ Complete |
| U8 | **The upload-rejection message interpolates the model's description raw**, producing "This looks like A screenshot of a web form…., not a plant." — capitalised mid-sentence, with the description's own full stop left in. Seen on the first live run. | Cosmetic; the message is still comprehensible and the rejection itself is correct. | Lowercase the first character and strip trailing punctuation before interpolating, in the rejection copy. |
| U9 | **A diagnosis can come back with no candidates at all.** `natural-senescence-old-leaf-yellowing` produced an empty differential on the 2026-08-19 run, having been top-1 on the run before — the second time that same case has returned nothing across the runs recorded here. This is the model declining to answer rather than answering wrongly, which is the better failure of the two, but the owner still gets a run they paid and waited for and no differential at the end of it. | Recorded rather than fixed, because it was found by the evaluation rather than reported by a user, and nothing in the retrieval rework addresses it. It is visible in the score as a top-1 *and* top-3 miss, so it is not hiding. | Find out which it is first: a refusal the confidence floor is producing, a structured-output failure being swallowed, or the model genuinely finding no candidate it can argue for. The `other` category holds only two cases, so one of them is fifty points of that category — its 50.0% top-1 in `eval/REPORT.md` is this case and nothing else. |

---

## Can affect a maintainer

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| M1 | **~~Coverage margin is ~5 statements wide.~~** *Largely resolved 2026-08-10.* It duly tripped on the next unrelated change (85.18%), so `ui/bootstrap.py` — real-infrastructure wiring with nothing unit-testable in it — was `omit`ted from `[tool.coverage.run]`, taking the total to 87.55%. ~~`ui/pages/*` and `ui/components/*` still count in the denominator at a structural 0%, so the underlying shape remains.~~ ~~*If it tightens again, fold the `ui` marker into the gated run rather than omitting more.*~~ **Resolved 2026-08-12 (Phase 2).** Marker-folding was tried and reverted (see `7769b45` / `4d7f3a2`); the owner chose the opposite fix instead, extending `omit` to `ui/pages/*` and `ui/components/*` on `ui/bootstrap.py`'s precedent (`890f9d7`). So the default gated `uv run pytest` run now neither exercises **nor measures** UI code, and the denominator no longer grows every time a page or component is added. | Omitting genuinely untestable wiring is honest; omitting the page modules is honest too *provided* the `ui` tier is actually run — they are meaningfully tested there, just not in the gated run, and a file that is tested shouldn't count as a gap. | **Run `uv run pytest -m ui` separately whenever UI code changes** — that tier, not the gated run, is what covers `ui/pages/*` and `ui/components/*`. The gate can no longer catch an untested page. |
| M2 | **The dose-detection regex misses spelled-out plural units.** `test_corpus_coverage.py` catches `5ml`, `2%`, `per litre`, but not "dilute 5 litres". | The corpus is hand-authored and reviewed, not generated; the abbreviated forms are the realistic risk. | Widen the pattern when the corpus stops being hand-authored. |
| M3 | **Two configuration lines are inert but read as guarantees.** `pyproject.toml`'s `filterwarnings` targets `plantopia.*`, which matches no module here (packages are `agent`, `core`, `tools`, …), so "error on our own DeprecationWarnings" is unenforced. `data/db.py`'s `PARSE_DECLTYPES` does nothing because every temporal column is declared `TEXT` and parsed by hand. | Both are harmless today and were specified in the plan. | Correct the regex to the real package names; drop `PARSE_DECLTYPES`. |
| M4 | **`retrieved` carries two score scales.** Tavily relevance scores are appended to a list of Chroma cosine scores. | This is *not* the §10.4 violation — that concerns text vs. image, which are kept strictly apart. The escalation gate has already fired by this point and nothing downstream ranks on the merged list, and the UI labels web provenance. | Normalise, or keep web results in a third field, if anything ever ranks `retrieved` again. |
| M5 | **`tools/weather.py` reads the wall clock** instead of an injected clock, unlike every other dated computation. | Harmless for a 21-day window; tests mock HTTP and never assert on dates. | Thread `Deps.now` through if the window ever becomes assertion-relevant. |
| M6 | **~~`tests/conftest.py` constructs `Settings(...)` which still honours `env_file=".env"`.~~** *Resolved 2026-08-13 (Phase 3) — every test-side `Settings(...)` construction now passes `_env_file=None`.* The risk was theoretical when this row was written, because the local `.env` at the time held only `PLANTOPIA_OPENROUTER_API_KEY`. It materialised the moment a second key (`PLANTOPIA_TAVILY_API_KEY`, added while wiring up LangSmith) landed in that file: `test_settings_applies_defaults` started asserting `tavily_api_key is None` against the real key read straight out of `.env`, failing the gated suite and blocking the coverage gate. Fixed at every construction site, not just the one that happened to fail first — `tests/conftest.py`'s `make_deps`, the `_settings()`/factory helpers in `test_web_search.py`, `test_guards.py`, `test_tracing.py`, `test_enrich.py`, and the inline `Settings(...)` calls in `test_diagnose.py`, `test_context.py` and `test_config.py` itself. | No `.env` is committed, so CI and a fresh clone are unaffected — this could only ever bite a developer's own machine, which is exactly what happened. | ✓ Complete |
| M7 | **Test-suite runtime grew from ~4s to ~34s**, almost entirely the parametrised corpus sweeps (six checks × 43 documents). | Still fast enough for a pre-commit loop. | `pytest-xdist` if it keeps growing. |
| M8 | **`store_upload` leaves orphan files** when a later upload in the same batch fails validation. | Disk litter only; no state references them. | Validate all, then write. |
| M9 | **Small coverage gaps in error paths:** the `RuntimeError` guard in `diagnosis_service`, `_escalation_query`'s output string, `invoke_structured`'s `method` passthrough, `tools_used` when a tool ran but returned nothing, `list_for_plant` multi-diagnosis ordering. | Each is a narrow branch whose behaviour is obvious from reading; none carries a safety property. | Add cases opportunistically when touching those files. |
| M10 | **~~`RoadmapRepository.mark()` on an unknown `step_id` silently no-ops (no `rowcount` check).~~** *Resolved 2026-08-12 — added `cursor.rowcount` check that raises ValueError, wired to UI via PlantService.mark_roadmap_step.* The Phase 2 UI button now validates correctly. | Fixed by adding proper rowcount validation. | ✓ Complete |
| M11 | **Repository read methods are unused in Phase 1** (`PlantRepository.get/delete`, the observation and diagnosis getters, most of the roadmap repository). ~~*Nothing — Phase 2 consumes them.*~~ **Narrowed 2026-08-12 (whole-branch review):** Phase 2 consumes most but not all. Now in use: `PlantRepository.get`/`list_all`, `ObservationRepository.list_for_plant`, `DiagnosisRepository.latest_for_plant`/`list_for_plant`, `RoadmapRepository.list_for_plant`/`mark`. Still unconsumed after Phase 2: **`PlantRepository.delete`** and **`RoadmapRepository.due_before`**, plus the single-row `ObservationRepository.get`/`DiagnosisRepository.get` getters. | Deliberate forward work: they are the Phase 2 contract and are tested. | `due_before` is what a care-queue/notification feature would use (the planned due-steps queue reads `list_for_plant` per plant instead); `delete` needs a "remove this plant" UI that no phase has planned yet. Drop either if the feature it was built for stays unplanned. |
| M12 | **~~`token_usage_json` and `cost_usd` are never written at all.~~** *Resolved 2026-08-13 (Phase 3) — a run-scoped `UsageCollector` (`core/cost.py`) is attached to every graph invoke as a callback and read by `persist` inside its existing transaction. Cost comes from OpenRouter's reported usage rather than a price table.* | Fixed. | ✓ Complete |
| M13 | **`"Plantopia"` is hardcoded in the rejection copy** with no name constant. | One occurrence. | Extract if the product is ever renamed. |
| M15 | **The checkpoint database grows by ~100 MB per diagnosis.** `ImageRef.data_b64` puts whole images in graph state, and LangGraph re-serialises the entire state at every superstep. Measured on 2026-08-10: two completed diagnoses of 3 MB photographs produced 205 MB of checkpoint blobs (~6.4 MB × 29 rows) against a 69 KB main database. | Not noticed until the code tour, because no test uses a realistic image and the main database looks tiny. Nothing breaks — it is disk consumption, not corruption. | Drop `images` from state after its last consumer (`enrich`'s image path), or carry only `ref` and load bytes on demand. Downscaling uploads (U3) would cut it by roughly four on its own. Old threads can be deleted; nothing reads a checkpoint after its run completes. |
| M14 | **The corpus parser is permissive in two ways:** an empty section body reports as *missing* rather than *empty*, and duplicate headings in one document silently overwrite. | Neither can pass the coverage test, so a malformed document fails loudly at the suite rather than at runtime. | Distinguish the two error cases if corpus authoring is ever delegated. |
| M16 | **Chat context and its checkpoint file both grow without bound.** Giving the chat agent a real checkpointer (`a62944f`) means every `send` replays the *entire* conversation history to the model — token cost per turn grows linearly with thread length, and a long enough thread eventually exceeds the model's context window. The checkpointer's own SQLite file (`{db_path}.chat-checkpoints`, wired in `ui/bootstrap.py`'s `get_chat_service`) is never pruned, the same shape of issue as M15 but for chat threads instead of diagnosis runs. | Conversation memory was the point of the fix; no thread in testing has come close to either limit. | Summarise or drop older turns before they reach the model (e.g. keep only the last *N* exchanges, or periodically compact with a summarisation call), and delete or archive old chat threads' checkpoint rows the way M15 proposes for diagnosis threads. |
| M17 | **Chat token usage and cost are not tracked.** The `messages` table has no usage columns, and adding them would require the project's first schema migration — against the property Phase 2 deliberately preserved by building the whole schema up front. Diagnosis runs *are* tracked (`M12`). | Chat spend is small next to a vision-plus-reasoning diagnosis, and the Medium 1 claim is satisfied by diagnosis cost. Recorded rather than left silent. | Add `token_usage_json`/`cost_usd` to `messages` together with an `ALTER TABLE` migration path in `data/db.py`, and give `ChatService` the same thread-scoped collector `DiagnosisService` uses. |
| M18 | **A run that spends tokens but produces no differential records nothing at all.** `agent/nodes/persist.py` returns early when `state.differential is None`, so a diagnosis that burned gate, vision and reasoning calls and then failed to produce a differential writes no row — and therefore no `token_usage_json` or `cost_usd` either. `M12` is fixed for diagnoses that *succeed*. The cost badge not rendering on that path (`ui/pages/diagnose.py`) is the visible half of the same gap, not a separate issue. | The early return is correct as persistence — there is no diagnosis to store, and inventing a row with a null differential would put a broken record in the timeline that the owner cannot act on. Spend on failed runs is the smaller loss. | Either write an observation-only row for a failed run, or record the run's usage somewhere that is not the `diagnoses` table. The collector already has the numbers (`config["configurable"]["usage_collector"]`); only the destination is missing. |
| M19 | **The evaluation measures reasoning and retrieval only — the vision layer is structurally invisible to it.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so no metric in `eval/REPORT.md` says anything about species identification or symptom extraction from a photograph. An image-based golden set was considered and deliberately deferred. | The metrics Ragas provides are retrieval-and-generation metrics that cannot see vision regardless, and licence-checked, *reliably labelled* photographs are hardest to source exactly where the agent is weakest (nutrient deficiencies, whose visual diagnosis is genuinely ambiguous even for an expert). A mislabelled golden image yields a confidently wrong metric, which is worse than an absent one. | Build an image-based golden set as its own spec. The stability evidence below makes vision the prime suspect for the instability recorded in [First live run](#first-live-run), so this is the measurement most worth buying next. ~~Note it would not address the nutrient weakness, which occurs with perfect symptom input.~~ *Amended 2026-08-19 — that caveat has expired: the nutrient weakness was closed by [the retrieval rework](#full-ragas-coverage-and-the-retrieval-rework-2026-08-18--19) without touching vision, so this is now the only major measurement gap left rather than one of two.* |
| M20 | **~~Roughly half of every Ragas judge call fails, so the four RAG metrics are means over 13–18 of 28 cases.~~** *Resolved 2026-08-18 — every metric now scores 28 of 28. See [Full Ragas coverage, and the retrieval rework](#full-ragas-coverage-and-the-retrieval-rework-2026-08-18--19).* Measured on the 2026-08-14 run: **51 of 112 judge jobs failed** — 39 `APIConnectionError`, 12 `TimeoutError` — against OpenRouter, *already* at `RunConfig(timeout=300, max_workers=4)` rather than Ragas's 180s/16-worker defaults. The failure rate is invisible in the scores themselves because Ragas emits NaN for a failed cell and `pandas.mean` skips it; `eval/report.py` discloses the per-metric counts precisely so this cannot hide again. Top-1/top-3 accuracy and the stability figures are unaffected — they are computed by `eval/metrics.py` from the pipeline runs, which had a 0% failure rate across both runs. | The disclosure is the important half, and it is in place: a reader sees "13 of 28 scored" and knows not to over-read the number. Chasing the transport failure is a separate problem from measuring the agent, and the metrics that matter most for diagnosis quality do not depend on the judge. | ✓ Complete — but note that the diagnosis in this column was wrong, and a probe is what corrected it. Rate limiting was ruled out (no 429s), as were timeouts (Ragas's 300s ceiling was never reached) and malformed rows (three metrics scored every row of the same data). Connections were simply dying under sustained concurrency, and `raise_exceptions=False` turned each death into a silent NaN. Four changes fixed it: the model client retries six times rather than the OpenAI default of two — applied application-wide, since the same transient would cost a real diagnosis its result; Ragas runs two workers rather than four; **each metric gets its own `evaluate()` call**, which was the structural fault, because ~280 judge calls in one long-running call let failures accumulate across every metric, heaviest first — exactly the 2/4/4/5 pattern; and NaN cells are re-submitted once, which is cheap because failures are independent between calls. |
| M21 | **~~The Ragas judge failure rate is far higher than `M20` records.~~** *Resolved 2026-08-18 with `M20`.* Gate 2 scored only **4, 4, 2 and 5 of 28 cases** across context precision, context recall, faithfulness and answer relevancy respectively. Gate 1 managed 17, 20, 11 and 16. A "Faithfulness 90.9%" computed over two cases is not a measurement. The disclosure added earlier is doing its job — the numbers are visibly qualified — but the underlying transport failure is worse than one run suggested. Cross-run comparison of the RAG metrics is unsafe. | Same as `M20`: the per-metric counts are shown alongside every score, so nobody reads Gate 2's numbers as unqualified. The transport failure, not the diagnosis pipeline, is what degraded. | ✓ Complete. Worth keeping for the lesson in what it cost to read those numbers: faithfulness fell from 90.9% to 64.6% once every row scored, and the 90.9% was the mean of **two cells**. The flattering figure was the artefact; the lower one is the measurement. No RAG figure recorded before 2026-08-18 is comparable with one recorded after. |
| M22 | **Context precision no longer scores the same passage set as the other three metrics.** It is computed over the passages *similarity ranked* only, while recall, faithfulness and answer relevancy still see everything the model read. Hypothesis-driven retrieval roughly doubled the contexts per row, and at ~50s per judge call fourteen contexts need some 700s of a row's own work against Ragas's 300s per-row deadline — so the metric timed out on every row and scored 0 of 28. The ceiling went to 2400s *and* the context set narrowed; either fixes it alone. | Deliberate, not a shortcut. Context precision asks what fraction of retrieved material was relevant, which is a question about *ranking* — and the look-alikes sections and the documents `hypothesise` named were fetched by id, on purpose, with no ranking to judge. Scoring a look-alikes section as a retrieval miss would mark down a mechanism working exactly as designed: it describes other disorders deliberately. All four metrics still report the same case total, so the narrower context set cannot be mistaken for fewer cases submitted. | Nothing, unless the metric's meaning drifts out of view. It answers "how well did similarity search rank" and not "how good was the material the model read" — those were the same question before `hypothesise` and are not now. Read it next to context recall, which does still cover everything. |
| M23 | **The tail of the differential is less stable than its head.** Candidate-set churn rose from 19.2% to ~22–23% over the same runs in which top-1 agreement rose to 100%: the leading diagnosis is now perfectly repeatable across five runs of byte-identical input, while the second and third candidates move around more than they used to. | The conclusion is what the owner acts on, and it is the half that got steadier. Recorded because the direction is worth watching rather than celebrating — a stable top-1 sitting on a less stable rationale is a weaker result than the headline suggests. | Nothing yet; it needs another run or two to say whether this is a trend or a wobble. If it holds, the question is whether `hypothesise`'s shortlist varies between repeats and drags the tail with it — logging the shortlist per repeat would answer that directly. |

| M24 | **The embedding provider does not reproduce its own vectors.** Embedding the same 87 query strings twice against `openai/text-embedding-3-small` through OpenRouter returned **38 different vectors of 87**, moving merged retrieval scores by up to **1.1e-3** and, in one of 28 golden cases, swapping the sixth of six results between two candidates 0.0011 apart. Measured 2026-08-25 while building a retrieval parity gate. | It is upstream — batching or hardware non-determinism at the provider — and the effect is far below the margins anything in this project decides on: the narrowest distance from a recorded best score to the 0.35 web-escalation threshold is 0.09, roughly eighty times the drift. | Nothing fixable here. What it rules out is any test that treats recorded embeddings as an exact baseline. It also means an evaluation run is not perfectly reproducible even at temperature 0 — a second source of variation alongside the model, worth remembering before reading a small change in `eval/REPORT.md` as a real one. |
| M25 | **The corpus lives in two places, and only one of them is used.** `corpus_chunks` (301 sections, 43 documents, 1536 dimensions) and `PgVectorRetriever` exist, are migrated, and are tested — and nothing consumes them. Retrieval runs on Chroma, as before. | Deferred deliberately on 2026-08-25, for two reasons that compound. The parity gate that would have justified the switch rested on replaying recorded query vectors, which `M24` shows cannot be an exact baseline. And the owner intends to reconsider the embedding model, which makes any comparison against the outgoing model's vectors worthless — the new path is to choose a model, embed the corpus into pgvector directly, and re-run the evaluation to establish fresh numbers rather than to prove nothing changed. | The sequence when it resumes: choose the embedding model; set `PLANTOPIA_EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` together (a stored vector's width is fixed by the column, so a different width needs a migration); run `python -m knowledge.ingest_corpus`; wire `PgVectorRetriever` into `agent/wiring.py`, `ui/bootstrap.py` and `eval/run_eval.py`; delete `ChromaRetriever`, `langchain-chroma` and `chromadb`; then run `python -m eval.run_eval` and record the result as a **new baseline**, not as a regression check — a different embedding model is expected to move top-1 and top-3, and the question is whether it moves them up. |

---

## Deliberate non-goals

Not limitations — deliberate decisions, taken in the sprint-4 plan and recorded here.

- **No reference-image corpus.** Image-to-image matching would likely beat cross-modal text matching for visually distinctive disorders, but sourcing licensed photographs for 43 disorders is a larger content job than the text corpus, and public plant datasets skew heavily to crop leaf pathology while barely covering the watering, light and nutrient problems that dominate houseplant failures. Revisit once the evaluation harness can measure whether it actually helps.
- **No authentication, no product recommendations, no notifications, no community features.**
- ~~**The learned user profile (Phase 4)** is planned, not missing.~~ *Built 2026-08-15.* Every phase planned for this project has now shipped: Phase 2 (plant profiles UI, the re-check flow, the chat agent, treatment feedback), all of Phase 3 (the Ragas evaluation harness, metrics, report renderer, CLI and the in-app Evaluation page, not just LangSmith tracing and cost display), and Phase 4's learned profile — durable facts extracted from diagnoses and chat, injected as priors, with their own page at `ui/pages/profile.py`. Nothing in this file is now waiting on a planned phase; the open rows are open on their own merits.

---

## First live run

2026-08-10, against a real (restricted, college-issued) OpenRouter key. A Monstera with
yellow leaf mottling, two photographs, indoor.

Everything on the main path fired: the gate rejected a non-plant image and passed the
real one, the vision model identified *Swiss cheese plant* and extracted symptoms, the
reasoning model selected four clarifying questions and produced a three-candidate
differential with a four-step treatment plan, retrieval returned six corpus passages,
and one plant, one observation, one diagnosis and four roadmap steps landed in SQLite.
LangGraph's interrupt-and-resume checkpointing behaved — the `select_questions` split
made during implementation held up outside the tests.

Three defects came out of it that no test had caught, because all three depend on
running with the image path switched off — a configuration that did not exist until
that morning:

1. **The model fabricated visual evidence.** Its user-visible reasoning said "the
   visually similar reference material corroborates the symptoms described" when no
   such material had been supplied. `_build_case` omits the section when empty, but
   the system prompt describes it unconditionally, and the model filled the silence.
   Fixed by stating the absence explicitly rather than leaving it out.
2. **`tools_used` reported `search_by_photograph`** on every diagnosis with images,
   including when no image embedder was wired and the search structurally could not
   run. Fixed by asking the retriever whether it supports image search at all.
3. **The rejection copy's grammar** — carried as U8 above.

The first two are worth dwelling on: both were *introduced* by disabling cross-modal
retrieval, and both were invisible to a test suite whose fixtures all supplied a
working image path. The generalisable lesson is that turning a feature off is a
behaviour change needing its own coverage, not merely the absence of one.

### Diagnostic stability is unmeasured, and the first evidence is not reassuring

Re-running the *same two photographs* with the same answers, to verify the fixes above,
produced a completely different differential: **Root Rot 60% / Insufficient Light 30% /
Magnesium Deficiency 10%** on the first run, **Rust 60% / Fungal Leaf Spot 30% / Natural
Senescence 10%** on the second. Same confidence, disjoint candidate sets, opposite
treatment plans — one says stop overwatering, the other says isolate the plant and apply
a fungicide.

Some variance is inherent at non-zero temperature, and the two runs did receive slightly
differently-worded pest questions, which the model generates. But a top candidate at 60%
that is not stable across identical input is a finding about diagnosis quality, not a
curiosity, and it is exactly what the Phase 3 Ragas evaluation harness exists to
quantify. Recorded here so that work starts from evidence rather than from scratch.

Note also that the contagion advice read "Move this plant away from Monstera today" for a
plant the owner had *named* Monstera — advice to move it away from itself. The prompt
gives the model `plant_name` and it used it to mean the other plants in the house.

### What the evaluation harness answered (2026-08-13)

The Phase 3 harness ran, and the question above now has a number. See
[`eval/REPORT.md`](../eval/REPORT.md) for the full table; the two findings worth carrying
here are these.

**Stability, on byte-identical input, is high — which relocates the suspicion rather than
dissolving it.** Repeating eight cases five times each gave **97.5% top-1 agreement** and
19.2% candidate-set churn. Clarifying-question drift over the same runs was **62.1%**: the
questions the model chooses vary enormously between runs, and the diagnosis barely moves.
That rules out the explanation floated above — that the earlier instability came from
"slightly differently-worded pest questions" — because question variance demonstrably does
not move the differential. What differs between the unstable observation and this stable
one is the *vision layer*, which the golden set injects past (`M19`). Symptom extraction is
now the prime suspect, and it is the one layer this harness structurally cannot see.

**Nutrient deficiencies fail, and they fail for a reason retrieval cannot explain.** Every
category recovers to 100% at top-3 except nutrient, which scored **33.3% top-1 and 33.3%
top-3** across six cases — when it is wrong, the correct cause is absent from the
differential entirely, not merely mis-ranked. The sprint-4 plan predicted the concentration
("nutrient deficiencies are notoriously confusable with each other") but not the mechanism,
and the mechanism is not confusion between nutrients: the misses reach for
`low-humidity`, `underwatering`, `insufficient-light` and `salt-buildup`.

A retrieval probe over the six cases settles where the fault is not:

| Case | Ground-truth doc retrieved at | Diagnosed |
|---|---|---|
| `calcium-deficiency` | **rank 1** | wrong |
| `nitrogen-deficiency` | **rank 2** | wrong |
| `potassium-deficiency` | rank 4 | wrong |
| `phosphorus-deficiency` | rank 6 | wrong |
| `iron-deficiency` | rank 1 | correct |
| `magnesium-deficiency` | rank 1 | correct |

For two of the four failures the correct document was in front of the model at rank 1–2 and
it still omitted the cause. So this is a **reasoning and ranking weakness, not a retrieval
or corpus-content gap** — which also means neither a larger corpus nor a reference-image set
(`M19`) would address it. One recurring distractor is visible in the probe:
`natural-senescence` appears in the top four retrieved documents for five of the six
nutrient cases, and an old leaf yellowing is exactly what a deficiency looks like.

The probe itself is worth a caution. A first attempt appeared to show catastrophic,
query-insensitive retrieval; it was passing a bare string to `ChromaRetriever.search`, whose
parameter is `queries: Sequence[str]`, so Python iterated the string and embedded each
*character* as a query. Self-query sanity-checking (feed a document's own text back and
require it to rank first) is what caught it.

### Two gates on the learned user profile (2026-08-15)

Phase 4 added durable facts about the owner, injected as priors into diagnosis and chat.
Two runs of the golden-set harness measured whether that injection changes diagnosis, one
with an empty profile and one with a deliberately lopsided one.

**Gate 1 (empty profile):** top-1 75.0%, top-3 82.1% after separator normalisation, with
every per-category top-1 identical to the Phase 3 baseline. The profile injection is
provably inert when there is nothing to inject.

*The committed [`eval/REPORT.md`](../eval/REPORT.md) renders this same run at top-3 **78.6%**,
not 82.1%, and the two are not a contradiction.* That run was scored before separator
normalisation existed: the model returned `insufficient_light` where the corpus slug is
`insufficient-light`, and the scorer compared raw strings, so one correct diagnosis counted
as a miss. Normalising that single separator — and nothing else — yields 82.1%, exactly the
Phase 3 baseline. The report is generated from the stored results file and is left as the
honest record of what that run measured at the time; the scorer fix that followed changes
future runs only. Stability repeats are not serialised, so the stability figures in that
report were likewise computed without normalisation and cannot be recomputed without a
re-run.

**Gate 2 (lopsided "overwaterer" profile):** top-1 75.0% and top-3 82.1%, all seven
per-category scores identical to Gate 1 — **but the profile was not ignored.** 7 of 28
cases produced a different candidate list and 15 of 28 asked different clarifying
questions. What moved were third-place candidates (`fertiliser-burn`,
`bacterial-leaf-spot`, `thrips`), none of them watering-related.

**Interpretation:** a deliberately lopsided watering prior changed the model's reasoning
without pulling the leading diagnosis toward water in any category. That is what the
"evidence takes precedence" framing in the injected block was built to produce.

**The bound, stated plainly:** 28 cases, 4 of them watering. This says the effect did not
reach the top candidate — not that no effect exists. Do not read it as though the hazard
is closed.

### Full Ragas coverage, and the retrieval rework (2026-08-18 / 19)

Two independent problems were open at the end of Phase 4: the nutrient category failed at
33.3% on *both* top-1 and top-3, and half the Ragas judge calls were dying (`M20`, `M21`).
Both are now closed, and the order matters — the instrument was fixed first, because
measuring the retrieval change against a broken judge would have proved nothing.

**The nutrient failure was never a corpus gap, and only partly a ranking one.** Three
changes to what `diagnose` is handed came first. Only sections describing a disorder
*itself* can earn a retrieved slot, because a look-alikes section recites the symptoms of
the disorders it rules out and is therefore an attractor for exactly the wrong query — on a
nitrogen case, `phosphorus-deficiency`'s look-alikes section scored 0.517 against
`nitrogen-deficiency`'s own symptoms at 0.508. One passage per disorder, so *k* slots
describe *k* candidates rather than letting a broadly-worded document take three of six
— every nutrient case had been retrieving six passages covering four disorders, the
distractor holding three and the answer holding one, which reads to the model as the
distractor being better supported, because it is better represented. And each shortlisted
disorder contributes its look-alikes section fetched *by id*, since that is the material
that discriminates between candidates and it can never win on similarity against the
symptom sections it would have to outrank.

That took the correct document into the shortlist in 23 of 28 cases and did **not** fix
nutrient, which is the useful part of the result: with the pipeline's real queries the
correct document sat at rank 16, 17, 21, 24 and 35 of 43 in the five failing cases. Raising
*k* from 6 to 15 moved nothing. No cap or reordering reaches rank 35.

**What fixed it was giving up on rank.** The clue was a case that already passed —
`mealybugs`, diagnosed correctly with its reference document at rank 35. The model's own
knowledge was outperforming the retriever, so `hypothesise` asks it to *name* the disorders
worth reading about from the ids the corpus holds, and `enrich` fetches those directly.
Correct document in front of the model: **28 of 28**. Nutrient went 33.3% → 66.7% → 83.3%
top-1 and 33.3% → 83.3% → 100% top-3 across the two runs that followed, and phosphorus
deficiency — absent from the differential entirely one run earlier — became top-1. Headline
top-1 rose 75.0% → 89.3%.

Three cautions on that result:

- **It is a lopsided-profile run.** Both figures come from `--profile overwaterer`, and no
  neutral run has been made since `hypothesise` landed. The 75.0% → 89.3% comparison is
  clean because both sides are `overwaterer`, but the current `empty` baseline is unmeasured.
- **The light category is not comparable across this boundary.** `insufficient-light-etiolation`
  was rewritten (`a9afa54`) because it contradicted the corpus it tested against: it expected
  `insufficient-light` for "stem stretched with widely spaced leaves", which both corpus
  documents call etiolation in as many words. It was also unwinnable as a pair with its
  sibling case — near-identical symptoms, opposite ground truth, each listing the other as
  `also_acceptable`, so no system takes top-1 on both except by guessing. Rewriting a case the
  pipeline *fails* deserves stating plainly: it was not a fix for the score, and the light
  category now measures a different case.
- **Headline accuracy was flat between the last two runs** (89.3%/96.4% both times) because
  `natural-senescence` moved the other way and returned an empty differential — now `U9`.

**The judge failures were not what `M20` guessed.** No 429s, no timeouts, no malformed
rows; connections were dying under sustained concurrency and `raise_exceptions=False` was
turning each into a silent NaN. The structural fault was putting ~280 judge calls into one
`evaluate()` call, where failures accumulated across every metric heaviest-first — which is
precisely the 2/4/4/5 pattern Gate 2 showed. Per-metric calls, a six-retry client budget,
two workers, and a re-submit pass for NaN cells took every metric to 28 of 28. The cost of
having read the old numbers: faithfulness "90.9%" was the mean of two cells and is 64.6%
when every row scores. Runtime roughly doubled to two hours, which is the price of the lower
concurrency.

**A failed case now gets one retry** (`d52db99`), on a fresh thread rather than resuming —
the first attempt's checkpoint may hold the state that failed. Which cases needed a second
attempt is recorded in the results file, because a retry that quietly rescued a case would
hide exactly the flakiness worth knowing about. Both runs above needed none, so their
"0 failed" is genuine rather than rescued.

**What this did not touch.** `M19` still holds: the golden set injects past the vision
layer, so none of these numbers say anything about species identification or symptom
extraction. That was the prime suspect for the instability in [First live
run](#first-live-run) before this work and remains so after it — with the nutrient weakness
now largely closed, an image-based golden set is the clear next measurement rather than one
of two competing candidates.

## Two plan defects caught during implementation

Worth recording because the review loop, not the tests, is what caught them.

1. **LangGraph replays a node body from the top on resume.** The plan put clarifying-question selection *inside* `gather_context`, before `interrupt()` — so the question-selection model call would have fired a second time on every resume, in production as well as in tests. Fixed by splitting `select_questions` into its own node, which checkpoints before the interrupt-only node runs.
2. **The plan's `role-injection` regex made one of its own tests unsatisfiable.** The line-anchored pattern could not match `system:` appearing mid-line, which the plan's own multi-pattern test required. Relaxed to word-boundary matching, accepted for a detector whose output is logging rather than blocking.
