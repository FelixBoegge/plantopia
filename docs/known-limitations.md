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
| U1 | **Parts of the pipeline still have not run live.** *Resolved for the main path on 2026-08-10* — see [First live run](#first-live-run). *The outdoor/weather branch was exercised live on 2026-08-31* — an outdoor run against Frankfurt am Main stored a 21-day series and a 7-day forecast, and its reasoning cited the photograph's age unprompted; an indoor run in the same session fetched nothing. *Web search was exercised live on 2026-08-31* — a Tavily key is configured and working, and `add-species-care-profiles` drives it on every researched care profile. Still unexercised against real APIs: the healthy-plant branch and the retake path. | The main path is now verified; the rest degrade rather than crash. | Run a case that triggers each: an outdoor plant with a town, a healthy plant, a deliberately blurry photo. |
| U2 | **~~The multimodal embeddings request shape is unverified.~~** *Resolved 2026-08-10, and the underlying feature is disabled.* The shape was never exercised because no multimodal embedding model is reachable at all: `google/gemini-embedding-2` (the old default) does not exist on OpenRouter, and `gemini-embedding-001`, the only real candidate, is data-policy blocked on restricted keys. `PLANTOPIA_MULTIMODAL_EMBEDDINGS` now defaults to `false`. | The slug came from a docs fetch and was flagged unverified precisely because it might be wrong. It was. | The request shape in `core/embeddings.py` remains unverified and will stay so until a multimodal embedder is reachable — re-check it against OpenRouter's reference at that point, not before. |
| U3 | **Uploads are not re-encoded or downscaled.** Pillow is a dependency but unused; four 8 MB images go to the vision model at full size. | No correctness impact; cost only. | Downscale in `core/images.py:store_upload` before base64 encoding. |
| U4 | **An unanswered boolean question is recorded as "no".** `ui/pages/diagnose.py` conflates "no" with "didn't say". | Only the mandatory drainage question is a choice; boolean questions are model-generated and rare. | Use a tri-state widget or omit unanswered keys from the answers dict. |
| U5 | **The low-confidence banner omits the escalation advice** PLAN §13.4 specifies — it names the distinguishing tests but never suggests a local nursery or extension service. | The substantive half (tests to run) is present. | One sentence in `ui/components/differential.py`. |
| U6 | **`calcium-deficiency` omits blossom-end rot**, the most recognisable calcium symptom in fruiting plants. | The corpus deliberately skews houseplant/ornamental; the document is correct for that scope. | Add a section if the corpus ever grows toward edibles. |
| U7 | **~~Rejected and retake paths do not rotate `thread_id`.~~** *Resolved 2026-08-12 — added `_rotate_thread()` helper called on both rejected and retake branches in ui/pages/diagnose.py.* State from the abandoned attempt stayed in the checkpoint and merged into the retry. **Amended 2026-08-12 (whole-branch review):** the first fix covered only the wizard. The re-check entry point derived its thread id as `recheck-{plant_id}-{latest_diagnosis_id}`, and neither a rejection nor a retake writes a diagnosis — so that id never changed and a second attempt resumed the abandoned run's checkpoint, the same bug class in the other entry point. `ui/pages/plant_detail.py` now appends a `recheck_attempt` counter that `_rotate_recheck_thread()` increments on both branches. | Fixed by rotating thread_id on both paths, in both entry points. | ✓ Complete |
| U8 | **The upload-rejection message interpolates the model's description raw**, producing "This looks like A screenshot of a web form…., not a plant." — capitalised mid-sentence, with the description's own full stop left in. Seen on the first live run. | Cosmetic; the message is still comprehensible and the rejection itself is correct. | Lowercase the first character and strip trailing punctuation before interpolating, in the rejection copy. |
| U9 | **A diagnosis can come back with no candidates at all.** `natural-senescence-old-leaf-yellowing` produced an empty differential on the 2026-08-19 run, having been top-1 on the run before — the second time that same case has returned nothing across the runs recorded here. This is the model declining to answer rather than answering wrongly, which is the better failure of the two, but the owner still gets a run they paid and waited for and no differential at the end of it. | Recorded rather than fixed, because it was found by the evaluation rather than reported by a user, and nothing in the retrieval rework addresses it. It is visible in the score as a top-1 *and* top-3 miss, so it is not hiding. | Find out which it is first: a refusal the confidence floor is producing, a structured-output failure being swallowed, or the model genuinely finding no candidate it can argue for. The `other` category holds only two cases, so one of them is fifty points of that category — its 50.0% top-1 in `eval/REPORT.md` is this case and nothing else. |
| U10 | **Identification accuracy is now measurable and still unmeasured.** Two methods identify the plant and each diagnosis records which one produced the species it was reasoned from — but no number anywhere says how often either is right. Golden cases supply their symptoms as text and are injected past `identify_plant` entirely, so `eval/REPORT.md` is silent about identification by construction, and this change does not alter that. What a person sees today is two answers and a choice, with nothing to tell them how much to trust either. | Measuring it needs an image-based golden set: photographs with a known species, which is a different dataset from the one that exists and a change of its own. What this adds instead is the two things that make the measurement possible later — a second, independent opinion to disagree with the first, and `species_method` on every diagnosis. | Build a small image set — fifty photographs with confirmed species across the corpus's categories — and score both methods on it separately. `species_method` also makes a cheaper proxy available first: on real runs, how often the two agree, and how often somebody overrides the leader. Neither is accuracy, but a rising override rate is evidence something is wrong. |
| U14 | **A researched care profile can be confidently wrong, and the only defence is a label.** The refusal gate compares the species the model says the material described against the species asked for, which catches the common failure — search drifting to a relative, as it does for *Ocimum africanum* — but not a model that echoes the asked-for name back regardless of what it read. That is the known weakness of asking a model to check its own work, and it is not solved here. | Every alternative is worse or much larger. Refusing everything the curated set does not cover is where this started, and it leaves 21 of the 28 golden species with no baseline at all. A second model checking the first costs another call and has the same weakness one level up. What is done instead is cheap and honest: the profile is labelled researched wherever a person reads it, carries the sources it was built from, and the diagnosis prompt is told to prefer the observed symptoms where the two disagree. | Sample the stored profiles once there are enough to be worth reading — the table is small, global, and every row names its sources, so checking twenty by hand is an afternoon rather than a project. A wrong one is evidence about the extraction, not about one owner's plant. |
| U15 | **A researched profile is never revisited.** No refresh, no expiry, and no way for anybody to say a profile is wrong. Once a species is researched, that row answers for it indefinitely — for every owner, since the cache is shared. | Deliberate scope. A correction mechanism needs somewhere to put the correction, someone trusted to make it, and a rule for what happens when two people disagree; that is a moderation feature, not a cache. The refusal gate and the label are what stand in for it, and a wrong row costs a misleading baseline rather than a wrong diagnosis — the prompt is told to prefer the observed symptoms. | A `researched_at` column already exists in effect (`created_at`), so an expiry is a `WHERE` clause whenever it is wanted. Deleting a row is the correction mechanism until there is a reason for a better one. |
| U12 | **~~Nothing tells the owner why the weather mattered.~~** *Resolved 2026-08-31 by `add-plant-timeline`: the recorded daily series is drawn against the observation it belongs to, as a chart with a sentence naming the notable days and a table carrying the same values for anybody who cannot see it.* What it said before: ** The diagnosis reasons against dated events — a frost on the 13th, a twelve-day drought ending the day before the photograph — and the owner sees only the reasoning's prose account of it. The series is stored, returned on the diagnosis endpoint, and typed on the client, and no screen draws it. | Deliberate, and the sequencing is the argument: `add-plant-timeline` has the surface a series belongs on, and drawing one now would mean designing that surface twice. The information is not lost — the reasoning cites it and the chat agent will answer questions from it — it is just not visual. | Draw it in `add-plant-timeline`, against the diagnosis it belongs to. The client types are already there (`WeatherSummary`, `WeatherDay`), so it is a rendering job rather than a plumbing one. |
| U18 | **An access token outlives the account it belongs to, for up to fifteen minutes.** `api/dependencies.current_owner` believes a token on its signature alone and reads no row, so deleting an account cannot make an outstanding token stop parsing. Refresh tokens are revoked, so the session cannot be extended; in the window, reads return nothing (there is nothing left) and writes fail on a foreign key to a `users` row that is gone. | Closing it means a database read on every request in the application, to defend against a threat that is the account's own owner holding their own token. The interface signs you out the moment the deletion succeeds, so in practice the token is discarded rather than held. The docstring on `current_owner` already recorded this trade before deletion existed; deletion is simply the first feature where it is visible. | If it ever matters, the cheapest version is a short-lived denylist of deleted user ids consulted only when a token's `iat` predates the last deletion — not a read on every request. Nothing today justifies it. |
| U19 | **An export does not carry the corpus passages a diagnosis cited.** A diagnosis in the archive names its evidence by reference; the text of the disorder document it drew on is not included, so a reasoning chain cannot be fully re-read offline. | The corpus is reference data, identical for everybody and unchanged by anything an owner does — including it would make every export larger to say the same thing, and would blur the line between "your data" and "the system's data" that the deletion rules depend on. | Include the cited passages if somebody actually asks to re-read one. The identifiers are in the archive, and the corpus is in the repository, so the join is possible today by hand. |
| U16 | **A timeline of two events is most plants.** Every plant in the development database has exactly one observation and one diagnosis, and every roadmap step in it is pending — so the timeline renders two events and no treatment history at all. It is correct and it is thin: the surface is built for a plant somebody has re-checked two or three times, and most plants are not that yet. | Nothing to fix. The value grows with the history, and the alternative — padding it with pending steps or chat turns — is the noise this deliberately keeps out. Recorded so that "the timeline looks empty" is understood as the data rather than the screen. | Nothing, unless re-checks stay rare enough to suggest the flow discourages them. That would be a finding about the re-check path, not about this. |
| U17 | **A skipped step and a step nobody ever did read the same on the timeline: they are both simply absent until settled.** Skipping is recorded and appears; never getting round to something is not an event and does not. Somebody scanning a history for "what did I actually do" sees the skips and the completions, and infers the rest. | The distinction the record makes is between *settled* and *pending*, and pending work belongs to the plan rather than to history. Marking the passage of an unmet due date as an event would fill a timeline with non-events. | The design's own open question, deferred deliberately: whether a lapsed step deserves a mark is a question about what an owner does with it, worth deciding against a real history rather than in advance. |
| U13 | **The staleness warning judges the date, not the plant.** A photograph eight days old is flagged; one seven days old is not, and neither judgement has anything to do with whether this particular plant changed. A cactus is the same cactus a month later; a wilting basil is a different plant by Thursday. | Seven days is a defensible constant and not much more — roughly the period over which the disorders in this corpus become visibly different, and a period a person can hold in their head. It is configuration (`PLANTOPIA_STALE_PHOTOGRAPH_DAYS`) so a deployment can move it. Making it depend on the species or the disorder would mean knowing both before the photograph has been looked at, which is the wrong way round. | If it ever matters: the threshold could vary by the primary candidate's severity once one exists — but that is after the diagnosis, and the warning's whole value is that it arrives before. A better version is probably per-species, which wants the care profiles `add-species-care-profiles` will build. |
| U11 | **The frontend works and has not been designed.** Every screen is assembled from shadcn/ui defaults with Tailwind utility classes applied where something needed to sit somewhere — there is no type scale, no spacing rhythm, no considered use of colour beyond severity, and nothing that would look deliberate to somebody who does not already know what it does. The wizard in particular now carries six or more fields at its pause and arranges them as a flat column. Raised by the owner on 2026-08-31 after the first real run through the whole flow. | Carried, and carried on purpose. Every change so far has been about whether the thing is *right* — that a diagnosis is honest about its confidence, that a wrong species is correctable, that a position is never stored precisely — and appearance is the one kind of wrong that is obvious to everybody and therefore never gets forgotten. The accessibility work is done and is the part that is expensive to retrofit: colour is never the only carrier of meaning, every path is reachable by keyboard, focus moves deliberately, and axe runs over every route. A visual pass sits on top of that rather than fighting it. | Its own change, after the remaining functional ones. Worth doing as a whole rather than screen by screen: a type scale, spacing, how a differential's candidates are ranked visually rather than only in order, and what the pause looks like now that it asks six questions instead of three. The browser tests locate by role and label rather than by class, so they should survive a restyle — which is itself worth checking, because a suite that breaks on every visual change is a suite that discourages visual change. |

---

## Can affect a maintainer

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| M1 | **~~Coverage margin is ~5 statements wide.~~** *Largely resolved 2026-08-10.* It duly tripped on the next unrelated change (85.18%), so `ui/bootstrap.py` — real-infrastructure wiring with nothing unit-testable in it — was `omit`ted from `[tool.coverage.run]`, taking the total to 87.55%. ~~`ui/pages/*` and `ui/components/*` still count in the denominator at a structural 0%, so the underlying shape remains.~~ ~~*If it tightens again, fold the `ui` marker into the gated run rather than omitting more.*~~ **Resolved 2026-08-12 (Phase 2).** Marker-folding was tried and reverted (see `7769b45` / `4d7f3a2`); the owner chose the opposite fix instead, extending `omit` to `ui/pages/*` and `ui/components/*` on `ui/bootstrap.py`'s precedent (`890f9d7`). So the default gated `uv run pytest` run now neither exercises **nor measures** UI code, and the denominator no longer grows every time a page or component is added. | Omitting genuinely untestable wiring is honest; omitting the page modules is honest too *provided* the `ui` tier is actually run — they are meaningfully tested there, just not in the gated run, and a file that is tested shouldn't count as a gap. | ~~**Run `uv run pytest -m ui` separately whenever UI code changes.**~~ **Moot from 2026-08-25:** Streamlit was retired with the auth change, and `ui/`, `tests/ui/` and the `ui` marker went with it. Nothing is omitted from coverage for being tested in another tier, and `api/` and `identity/` are now measured in the gated run. |
| M2 | **The dose-detection regex misses spelled-out plural units.** `test_corpus_coverage.py` catches `5ml`, `2%`, `per litre`, but not "dilute 5 litres". | The corpus is hand-authored and reviewed, not generated; the abbreviated forms are the realistic risk. | Widen the pattern when the corpus stops being hand-authored. |
| M3 | **Two configuration lines are inert but read as guarantees.** `pyproject.toml`'s `filterwarnings` targets `plantopia.*`, which matches no module here (packages are `agent`, `core`, `tools`, …), so "error on our own DeprecationWarnings" is unenforced. ~~`data/db.py`'s `PARSE_DECLTYPES` does nothing because every temporal column is declared `TEXT` and parsed by hand.~~ *The second half resolved 2026-08-25:* the sqlite3 driver is gone and every temporal column is a real `timestamptz`, parsed by the driver. | The `filterwarnings` half is still harmless and still misleading. | Correct the regex to the real package names. A schema test now asserts that no timestamp column is declared without a timezone, so the half that was fixed cannot quietly regress. |
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
| M15 | **~~The checkpoint database grows by ~100 MB per diagnosis.~~** *Resolved 2026-08-25.* `ImageRef` carries a blob key rather than base64, so graph state no longer scales with the size of the photographs a diagnosis was given. Measured before: two diagnoses of 3 MB photographs produced 205 MB of checkpoint blobs, because LangGraph re-serialises the whole state at every superstep. Measured after, in `tests/unit/agent/test_state_size.py`: four 4 MB photographs, and the state referencing them serialises to under a kilobyte — with a second test asserting that state size does not grow with photograph size at all. | Fixed. | ✓ Complete. Note what it did *not* fix: the full-size image still goes to the vision model on every diagnosis, which is `U3` and is cost rather than storage. |
| M14 | **The corpus parser is permissive in two ways:** an empty section body reports as *missing* rather than *empty*, and duplicate headings in one document silently overwrite. | Neither can pass the coverage test, so a malformed document fails loudly at the suite rather than at runtime. | Distinguish the two error cases if corpus authoring is ever delegated. |
| M16 | **Chat context and its checkpoint file both grow without bound.** Giving the chat agent a real checkpointer (`a62944f`) means every `send` replays the *entire* conversation history to the model — token cost per turn grows linearly with thread length, and a long enough thread eventually exceeds the model's context window. The checkpointer's rows are never pruned, the same shape of issue as M15 but for chat threads instead of diagnosis runs. *Amended 2026-08-25:* the SQLite file this originally named is gone — checkpoints are Postgres rows and the service is wired in `api/dependencies.chat_service`. The unbounded growth is unchanged. | Conversation memory was the point of the fix; no thread in testing has come close to either limit. | Summarise or drop older turns before they reach the model (e.g. keep only the last *N* exchanges, or periodically compact with a summarisation call), and delete or archive old chat threads' checkpoint rows the way M15 proposes for diagnosis threads. |
| M17 | **Chat token usage and cost are not tracked.** The `messages` table has no usage columns. ~~Adding them would require the project's first schema migration — against the property Phase 2 deliberately preserved by building the whole schema up front.~~ **That reason expired on 2026-08-25:** Alembic owns the schema now, and adding a column is a generated migration rather than an argument. | Chat spend is small next to a vision-plus-reasoning diagnosis, and the Medium 1 claim is satisfied by diagnosis cost. What kept this open was the cost of the first migration; that cost is now paid. | `alembic revision --autogenerate` after adding `token_usage_json`/`cost_usd` to the model, then give `ChatService` the same thread-scoped collector `DiagnosisService` uses. |
| M18 | **A run that spends tokens but produces no differential records nothing at all.** `agent/nodes/persist.py` returns early when `state.differential is None`, so a diagnosis that burned gate, vision and reasoning calls and then failed to produce a differential writes no row — and therefore no `token_usage_json` or `cost_usd` either. `M12` is fixed for diagnoses that *succeed*. The cost badge not rendering on that path (`ui/pages/diagnose.py`) is the visible half of the same gap, not a separate issue. | The early return is correct as persistence — there is no diagnosis to store, and inventing a row with a null differential would put a broken record in the timeline that the owner cannot act on. Spend on failed runs is the smaller loss. | Either write an observation-only row for a failed run, or record the run's usage somewhere that is not the `diagnoses` table. The collector already has the numbers (`config["configurable"]["usage_collector"]`); only the destination is missing. |
| M19 | **The evaluation measures reasoning and retrieval only — the vision layer is structurally invisible to it.** Golden cases supply symptoms as text and are injected past `identify_plant` and `assess_symptoms`, so no metric in `eval/REPORT.md` says anything about species identification or symptom extraction from a photograph. An image-based golden set was considered and deliberately deferred. | The metrics Ragas provides are retrieval-and-generation metrics that cannot see vision regardless, and licence-checked, *reliably labelled* photographs are hardest to source exactly where the agent is weakest (nutrient deficiencies, whose visual diagnosis is genuinely ambiguous even for an expert). A mislabelled golden image yields a confidently wrong metric, which is worse than an absent one. | Build an image-based golden set as its own spec. The stability evidence below makes vision the prime suspect for the instability recorded in [First live run](#first-live-run), so this is the measurement most worth buying next. ~~Note it would not address the nutrient weakness, which occurs with perfect symptom input.~~ *Amended 2026-08-19 — that caveat has expired: the nutrient weakness was closed by [the retrieval rework](#full-ragas-coverage-and-the-retrieval-rework-2026-08-18--19) without touching vision, so this is now the only major measurement gap left rather than one of two.* |
| M20 | **~~Roughly half of every Ragas judge call fails, so the four RAG metrics are means over 13–18 of 28 cases.~~** *Resolved 2026-08-18 — every metric now scores 28 of 28. See [Full Ragas coverage, and the retrieval rework](#full-ragas-coverage-and-the-retrieval-rework-2026-08-18--19).* Measured on the 2026-08-14 run: **51 of 112 judge jobs failed** — 39 `APIConnectionError`, 12 `TimeoutError` — against OpenRouter, *already* at `RunConfig(timeout=300, max_workers=4)` rather than Ragas's 180s/16-worker defaults. The failure rate is invisible in the scores themselves because Ragas emits NaN for a failed cell and `pandas.mean` skips it; `eval/report.py` discloses the per-metric counts precisely so this cannot hide again. Top-1/top-3 accuracy and the stability figures are unaffected — they are computed by `eval/metrics.py` from the pipeline runs, which had a 0% failure rate across both runs. | The disclosure is the important half, and it is in place: a reader sees "13 of 28 scored" and knows not to over-read the number. Chasing the transport failure is a separate problem from measuring the agent, and the metrics that matter most for diagnosis quality do not depend on the judge. | ✓ Complete — but note that the diagnosis in this column was wrong, and a probe is what corrected it. Rate limiting was ruled out (no 429s), as were timeouts (Ragas's 300s ceiling was never reached) and malformed rows (three metrics scored every row of the same data). Connections were simply dying under sustained concurrency, and `raise_exceptions=False` turned each death into a silent NaN. Four changes fixed it: the model client retries six times rather than the OpenAI default of two — applied application-wide, since the same transient would cost a real diagnosis its result; Ragas runs two workers rather than four; **each metric gets its own `evaluate()` call**, which was the structural fault, because ~280 judge calls in one long-running call let failures accumulate across every metric, heaviest first — exactly the 2/4/4/5 pattern; and NaN cells are re-submitted once, which is cheap because failures are independent between calls. |
| M21 | **~~The Ragas judge failure rate is far higher than `M20` records.~~** *Resolved 2026-08-18 with `M20`.* Gate 2 scored only **4, 4, 2 and 5 of 28 cases** across context precision, context recall, faithfulness and answer relevancy respectively. Gate 1 managed 17, 20, 11 and 16. A "Faithfulness 90.9%" computed over two cases is not a measurement. The disclosure added earlier is doing its job — the numbers are visibly qualified — but the underlying transport failure is worse than one run suggested. Cross-run comparison of the RAG metrics is unsafe. | Same as `M20`: the per-metric counts are shown alongside every score, so nobody reads Gate 2's numbers as unqualified. The transport failure, not the diagnosis pipeline, is what degraded. | ✓ Complete. Worth keeping for the lesson in what it cost to read those numbers: faithfulness fell from 90.9% to 64.6% once every row scored, and the 90.9% was the mean of **two cells**. The flattering figure was the artefact; the lower one is the measurement. No RAG figure recorded before 2026-08-18 is comparable with one recorded after. |
| M22 | **Context precision no longer scores the same passage set as the other three metrics.** It is computed over the passages *similarity ranked* only, while recall, faithfulness and answer relevancy still see everything the model read. Hypothesis-driven retrieval roughly doubled the contexts per row, and at ~50s per judge call fourteen contexts need some 700s of a row's own work against Ragas's 300s per-row deadline — so the metric timed out on every row and scored 0 of 28. The ceiling went to 2400s *and* the context set narrowed; either fixes it alone. | Deliberate, not a shortcut. Context precision asks what fraction of retrieved material was relevant, which is a question about *ranking* — and the look-alikes sections and the documents `hypothesise` named were fetched by id, on purpose, with no ranking to judge. Scoring a look-alikes section as a retrieval miss would mark down a mechanism working exactly as designed: it describes other disorders deliberately. All four metrics still report the same case total, so the narrower context set cannot be mistaken for fewer cases submitted. | Nothing, unless the metric's meaning drifts out of view. It answers "how well did similarity search rank" and not "how good was the material the model read" — those were the same question before `hypothesise` and are not now. Read it next to context recall, which does still cover everything. |
| M23 | **The tail of the differential is less stable than its head.** Candidate-set churn rose from 19.2% to ~22–23% over the same runs in which top-1 agreement rose to 100%: the leading diagnosis is now perfectly repeatable across five runs of byte-identical input, while the second and third candidates move around more than they used to. | The conclusion is what the owner acts on, and it is the half that got steadier. Recorded because the direction is worth watching rather than celebrating — a stable top-1 sitting on a less stable rationale is a weaker result than the headline suggests. | Nothing yet; it needs another run or two to say whether this is a trend or a wobble. If it holds, the question is whether `hypothesise`'s shortlist varies between repeats and drags the tail with it — logging the shortlist per repeat would answer that directly. |

| M27 | **~~Endpoint tenancy is exercised below HTTP.~~** *Resolved 2026-08-25.* `tests/api/test_endpoint_tenancy.py` now registers two accounts and issues every request with a bearer token for the second, so the resolution of a session to an owner is exercised along with the handler and the 404-not-403 mapping. The shared API client fixture signs in the same way, so no test reaches an owner-scoped route without going through the real resolution. | The table did not change; only how the owner is established did, which was the point of keeping that in one function. Verified by making the plant service ignore the resolved owner: thirteen of the table's cases fail. | ✓ Complete |
| M24 | **The embedding provider does not reproduce its own vectors.** Embedding the same 87 query strings twice against `openai/text-embedding-3-small` through OpenRouter returned **38 different vectors of 87**, moving merged retrieval scores by up to **1.1e-3** and, in one of 28 golden cases, swapping the sixth of six results between two candidates 0.0011 apart. Measured 2026-08-25 while building a retrieval parity gate. | It is upstream — batching or hardware non-determinism at the provider — and the effect is far below the margins anything in this project decides on: the narrowest distance from a recorded best score to the 0.35 web-escalation threshold is 0.09, roughly eighty times the drift. | Nothing fixable here. What it rules out is any test that treats recorded embeddings as an exact baseline. It also means an evaluation run is not perfectly reproducible even at temperature 0 — a second source of variation alongside the model, worth remembering before reading a small change in `eval/REPORT.md` as a real one. |
| M25 | **The corpus lives in two places, and only one of them is used.** `corpus_chunks` (301 sections, 43 documents, 1536 dimensions) and `PgVectorRetriever` exist, are migrated, and are tested — and nothing consumes them. Retrieval runs on Chroma, as before. | Deferred deliberately on 2026-08-25, for two reasons that compound. The parity gate that would have justified the switch rested on replaying recorded query vectors, which `M24` shows cannot be an exact baseline. And the owner intends to reconsider the embedding model, which makes any comparison against the outgoing model's vectors worthless — the new path is to choose a model, embed the corpus into pgvector directly, and re-run the evaluation to establish fresh numbers rather than to prove nothing changed. | The sequence when it resumes: choose the embedding model; set `PLANTOPIA_EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` together (a stored vector's width is fixed by the column, so a different width needs a migration); run `python -m knowledge.ingest_corpus`; wire `PgVectorRetriever` into `agent/wiring.py` and `eval/run_eval.py` (`ui/bootstrap.py` no longer exists — Streamlit was retired on 2026-08-25); delete `ChromaRetriever`, `langchain-chroma` and `chromadb`; then run `python -m eval.run_eval` and record the result as a **new baseline**, not as a regression check — a different embedding model is expected to move top-1 and top-3, and the question is whether it moves them up. |
| M26 | **The test suite needs a database.** `docker compose up -d db` is a prerequisite for `uv run pytest`: repository, blob-store, retriever and checkpoint tests run against real PostgreSQL. The suite's previous claim of making "no network calls" is retired — it now claims only, and absolutely, that it makes no LLM calls. | Deliberate. Mocking the database in a change whose subject is the database would produce tests that assert on the mock. Tests use a throwaway database created per session and dropped after, each test inside a transaction that is rolled back, so a run can neither see nor damage development data. | Nothing. The cost is that a contributor cannot run the suite without Docker, which the README now says in the first paragraph rather than leaving them to discover through a connection error. |
| M28 | **This deployment is one process, and three things now depend on that.** Rate-limit counters (`api/rate_limit.py`), the run executor's pool, and the event bus (`runs/bus.py`) all live in this process's memory. Two workers behind one address would permit twice the rate limit, run twice the configured pool, and — the one a user would notice — leave a client connected to process B watching a run on process A seeing an empty stream. The sweeper would also run twice, which is wasteful rather than wrong and is why `PLANTOPIA_RUN_SWEEPER_ENABLED` exists. The rate limiter's source is also whatever `request.client.host` reports, which behind a proxy is the proxy. | Deliberate for a single container, and recorded as one constraint rather than three because it has one fix. A shared store is a dependency, an availability question and a failure mode of its own, and none of that is worth carrying before there is a second process. The executor is behind a port for exactly this substitution. | **The deployment change must not scale this horizontally without substituting the bus and the limiter.** Redis or `LISTEN`/`NOTIFY` for the bus, Redis or the reverse proxy for the limiter, a real worker behind `RunExecutor`. Configure trusted forwarded headers regardless — that one matters sooner, because a proxy makes every visitor share one budget. |
| M29 | **~~The quota guard and usage recording are complete, tested, and unreached.~~** *Resolved 2026-08-26.* `services/run_service.start` calls `limits.check` before a run row exists, and `runs/worker` records usage on the way out of every terminal status — including cancelled, and including runs the sweeper ends, which are recorded with an unknown cost so that crashing is not a way to run for free. | The test that enforced the note (`test_limits_are_not_wired_yet`) failed the moment the guard was wired, which is what it was for, and was deleted with the note. | ✓ Complete |
| M30 | **A dropped refresh response signs the person out.** Refresh tokens rotate on use, so a client that retries a refresh whose response was lost presents a token that has already been spent — indistinguishable from a stolen one, and treated as one: the whole family is invalidated and the account signs in again. | Accepted, and the reason reuse detection is worth having. There is no way to tell the honest retry from the theft, and the alternative — tolerating one reuse — is the alternative of not detecting reuse. | **A frontend contract, not a fix: refresh is never retried.** A failed refresh sends the person to sign in. Recorded here because it is a rule the client has to follow and nothing in the API can enforce. |
| M31 | **Keep-alive emission on an event stream is not covered by a test.** The interval configured on the response is asserted (`tests/api/test_run_stream.py`), and so is the framing that keeps a ping from being read as an event — but that a ping is actually sent on an idle stream is not. `TestClient` does not surface `sse_starlette`'s comment lines through this handler however it is arranged; the attempts hung rather than failed, which is worse than no test. | The emission is the library's behaviour rather than this project's, and the half this code owns — passing the configured interval — is checked. The failure mode if it broke is a proxy closing an idle stream, which a client already recovers from by reconnecting with `Last-Event-ID`. | Exercise it against a real server rather than `TestClient` — the deployment change is where there is one to point at. A single curl against a running instance with a low `PLANTOPIA_RUN_KEEPALIVE_SECONDS` settles it. |
| M32 | **The automated accessibility pass cannot see colour contrast.** `web/src/accessibility.test.tsx` runs axe over every route, but it runs it in jsdom, which computes no styles — so `color-contrast` is skipped rather than failed, and the one criterion most likely to break from a palette change is the one the suite cannot check. Contrast was verified once, on 2026-08-26, by loading axe into a real browser against the dev server: no violations on any route with contrast actually running. That check is a thing somebody did, not a thing that runs. | Everything axe *can* check in jsdom is checked on every route on every run, and the rules it skips are skipped loudly enough to find (`incomplete`/absent, not passing). Wiring a real browser into the suite is the Playwright harness's job, and that harness arrives in this same change — but pointing it at axe as well would have been scope on top of the flows it exists for. | Add an axe pass to the Playwright suite once it is running: it already opens each route in Chromium, so it is an injected script and one assertion per page. That would move contrast, focus-visibility and anything else style-dependent from a dated note into a gate. |
| M33 | **~~The frontend's tests are a second command, and a contributor can forget it.~~** *Resolved 2026-09-01 by `add-continuous-integration`: `.github/workflows/ci.yml` runs ruff, the Python suite against a PostgreSQL service container, the frontend typecheck and unit suite, a production build, and Playwright — on every push and every pull request, with no secret required.* What it said before: ** `uv run pytest` is green whatever the state of `web/`: nothing in the Python gate compiles TypeScript, runs vitest, or opens a browser. The React work landed with three defects that the Python suite could not have seen and the component suite did not — a startup that fired two token renewals and revoked its own session, every clarifying question rendered as an unlabelled text box, and a plant created by a run that never appeared on the grid. | Recorded rather than fixed because the fix is CI, and there is no CI here yet. What is in place instead is the README saying plainly that there are two suites and that passing one says nothing about the other, plus three cross-language agreement tests that run inside the Python gate and read TypeScript source: `test_client_types.py`, `test_source_names_agree.py` and `test_question_shape_agrees.py`. Those cover the shapes; they cannot cover behaviour. | The deployment change adds CI, and both suites plus Playwright belong in it. Until then: if you change a screen, run `npm test` and `npx playwright test` as well. |
| M34 | **The browser tests cover four flows, not the application.** Registering and signing in, a diagnosis through the interrupt, a dropped stream, and a chat reply with a lookup. Not covered in a browser: password reset, cancelling a run, a rejected photograph, the account screen's forget-a-fact, the evaluation screen, and every failure path. | Those four were chosen as the ones a mock makes look easy and a browser does not, and the choice paid for itself — three of the defects above were found by exactly these flows. The rest have component tests, which is weaker evidence but not none. | Add a flow when a component test turns out to have been describing something that did not work, which is how each of these was earned. The harness is the expensive part and it now exists: a new flow is one file. |
| M35 | **One recorded Pl@ntNet response is the whole basis of the parsing tests.** The request shape, the organ vocabulary and the response fields were verified against the live service on 2026-08-26 — `habit` is accepted, an unknown organ fails the whole request with a 400, and omitting `organs` is accepted — and `tests/fixtures/plantnet_identify.json` is that response. What it does not cover: a species with no common name, a result the service ranks below its own confidence floor, a `noReject` refusal, and whatever their response gains in a future version. Those edge cases are tested by *mutating* the recording, which is one step better than inventing a body and one step worse than having seen one. | One recording is a large improvement on none, which is what `U2` was: a request shape read out of documentation, never exercised, and wrong. The adapter also treats an unrecognised response as a failure like any other, so a shape that changes underneath this degrades to the vision model's identification rather than breaking a diagnosis. | Record a second fixture the first time the service returns something the parser drops — the adapter logs it. A response version other than the recorded one is the signal to re-record; the service reports its version in every response, and nothing currently reads it. |
| M36 | **The identification prompt lost its hint, and nothing measures what that cost.** The vision model used to be given the owner's name for the plant. It is not any more — a model told the answer tends to return it, which would make agreement between the methods meaningless — and the identification is very likely slightly worse as a result. How much worse is unknown, for the same reason `U10` is unknown. | Deliberate, and the right way round: a confidently wrong species that nothing can contradict is worse than an honestly uncertain one, and independence is what makes contradiction possible. The cost is also bounded in practice, because the second method and the owner both get a say. | The image-based golden set in `U10` measures this too: run it with and without the hint. Until then the hint stays out. |
| M37 | **The two methods' confidences are not comparable, and the interface shows both.** Each candidate carries the number its own method produced, rendered in words. Nothing calibrates them against each other, so "very confident" from the vision model and "very confident" from the classifier are not the same claim — and a person choosing between them is being invited, gently, to compare two things that do not compare. | Every alternative is worse. Hiding confidence removes the only signal a person has; normalising them would invent a calibration nobody measured; picking a winner by number is the arithmetic this change explicitly refuses. Words rather than numbers at least blunt the false precision. | Calibration needs the same image set as `U10`. With it, both methods' scores could be mapped onto one scale of observed accuracy, and the words would then mean the same thing whichever produced them. |
| M38 | **The test photographs carried GPS coordinates, and git history still holds them.** `test_pics/*.jpg` were committed in `172c421` with a full GPS block — latitude, longitude and altitude of where they were taken, which is a home. The working copies were stripped on 2026-08-26, keeping their capture dates and pixels; the original blobs remain reachable in earlier commits. Camera make, model and software are still present in the stripped files, which identify a phone rather than a person. | Carried rather than closed because closing it means `git filter-repo` and rewriting every commit hash from that point, which is a decision about the repository rather than about the code, and was declined for now. Found while starting `add-image-metadata-capture` — the change whose entire purpose is coarsening exactly this data before it is stored, which makes the repository shipping the precise version worth recording rather than quietly fixing. | Before this repository is made public: `git filter-repo --path test_pics --invert-paths` and re-add the stripped files, or replace the photographs with ones carrying no personal metadata. Either rewrites history, so it wants doing before anything is pushed rather than after. |
| M39 | **This is the first change since the migration that the evaluation numbers should be expected to move under, and the baseline in `eval/REPORT.md` (2026-08-19) is no longer comparable.** The harness scripts the gate and vision tiers and uses a *real* reasoning model, which is the tier that selects clarifying questions — so rewriting that prompt to ask about a plant's recent treatment, and raising the count from at most two to three or four, changes what every golden case is asked and therefore what its `situation` string contains. Two metrics read that string directly (`answer_relevancy`, and the question-drift figure), and the diagnosis itself sees different context. | Carried rather than measured, because measuring it means an evaluation run and those cost about €1.50 each — the owner's standing constraint is to keep that spend low, and a run commissioned by me rather than asked for is exactly the spend they meant. The change is also not optional: asking what has already been done to a plant is what stops a treatment plan opening with something the owner did last week. | Run the harness once when the remaining functional changes are done, and record the new figures as the baseline rather than comparing them to the old ones. Comparing across this change would attribute a prompt rewrite to whatever else moved in between. |
| M40 | **~~The coarse position is stored and never read.~~** *Resolved 2026-08-31 by `add-granular-weather`: the position is now used directly wherever the owner accepted the place name derived from it, and the name wins wherever they changed it — a correction that lost to the coordinates behind it would be a control that does nothing. `tests/unit/agent/nodes/test_enrich.py::TestWhichPlaceIsLookedUp` covers accepted, corrected, case-insensitive, no position at all, and a position whose name never resolved.* What it said before: `observations.latitude` and `longitude` are written on every upload that carried a fix, and nothing queries them: the weather lookup still takes a *place name* and forward-geocodes it through Open-Meteo, so a position read from a photograph becomes a name and the name becomes a position again. Two geocoding round trips to arrive back where it started. | The name is what a person can confirm or correct, and the correction has to be the thing the run uses — otherwise somebody fixes a wrong town and the diagnosis quietly proceeds on the coordinates behind it. So the name is authoritative today and the position is recorded for later rather than used now. Recording it costs nothing and having to re-read every photograph later would cost everything, because the metadata is stripped on the way in. | `add-granular-weather` is where it earns its place: an hourly window and a forecast want coordinates rather than a town, and the position is already there and already coarse. The open question it inherits is which wins when both exist — recorded in that change's design rather than guessed here. |
| M51 | **There is CI and there is no deployment.** No Dockerfile, no application service in `docker-compose.yml` — which still brings up only the database — and nothing that produces a runnable artefact. The design's §10 specifies containers and this change deliberately delivered only its second half. | A decision, taken on 2026-09-01: the capstone review comes first, the hosting question is genuinely open (`openspec/config.yaml`: "hosting decided at deploy time"), and a running instance means a public URL against paid OpenRouter and Pl@ntNet keys. Verification is worth having now; deployment is worth deciding later. | Multi-stage Dockerfiles, an `api` and `frontend` service in compose, `alembic upgrade head` on API start, and `python -m knowledge.ingest_corpus` as a one-shot. `M28` constrains it: the rate limiter, the run executor pool and the event bus all assume one process, and none may be scaled horizontally without being replaced first. |
| M52 | **The Node version is pinned in CI and nowhere else.** `.github/workflows/ci.yml` names Node 22; `web/package.json` has no `engines`, there is no `.nvmrc`, and no `volta` key. So the machine and a developer's laptop can disagree, and the machine is the one that will be believed. | Accepted rather than overlooked. Vite 8, Vitest 4 and TypeScript 7 already imply a modern Node, and pinning it in the repository is a decision about local development that this change had no reason to make on its own. | An `.nvmrc` containing the same version CI uses, and a line in the README. Worth doing the first time a build behaves differently on somebody's machine than on the runner. |
| M49 | **Deleting an account failed outright on a deployment where nobody had run a diagnosis.** LangGraph creates its checkpoint tables in `PostgresSaver.setup()`, which runs when a checkpointer is first built — on the first diagnosis. Before that they do not exist, so the deletion sweep raised `psycopg.errors.UndefinedTable` and answered 500. Every unit test passed: they run against a database where earlier tests had already created the tables. | Not carried — fixed in `add-privacy-controls`. `agent/checkpoints._delete_where` now treats an absent table as zero rows removed, which is the honest answer, and gives each table its own transaction block so one missing table cannot poison the connection for the rest. | Done. Worth recording because of *how* it was found: a browser flow that signed up and immediately deleted, which is the exact shape of the person most likely to do it, and the only test in the suite that ran against a database where no diagnosis had ever happened. |
| M50 | **`recheck_thread` has no production caller and has not had one since the Streamlit UI was deleted.** It builds a thread id from plant, diagnosis and attempt — the derived scheme whose collisions `U7` records. Every run now gets a fresh `diagnosis_thread(user_id)` with a random component, initial or re-check alike, so nothing needs it. | Left in place rather than deleted. Its tests also exercise `owner_of` and `verify_owner`, which account deletion genuinely depends on, and removing the function would mean editing those. It is not a correctness risk — it carries the owner prefix like every other thread id — only dead. | Delete it with its tests when somebody is next in `agent/threads.py`, keeping the `owner_of`/`verify_owner` coverage. |
| M47 | **`/diagnoses/:id` was linked from the plant page and never routed.** "See the full differential" has pointed at it since the React frontend landed; there was no such route, so it fell through the catch-all and silently redirected to the plants list. Component tests asserted the `href` and the browser test asserted the link was *visible* — nothing ever clicked it. Found while writing a timeline flow that did. | Not carried: fixed in `add-plant-timeline`, which would otherwise have multiplied one dead link into one per diagnosis event. Every part already existed — the endpoint, the `useDiagnosis` hook, and `<Differential>`, which takes exactly the shape the endpoint returns — so the fix was the route and a twenty-line screen. | Done. The lesson generalises and is the reason the new browser flow *follows* the link rather than asserting on it: an assertion that a link exists is not an assertion that it goes anywhere, and this codebase now has one example of the difference costing a whole route. |
| M48 | **Timeline dates are formatted in the viewer's locale, and two test environments disagree about what that renders.** `toLocaleDateString` produces "10 August 2026" under jsdom and "August 10, 2026" in Chromium. A component test pinned the first and the browser test failed on the second. | Correct behaviour — a date should read the way the reader expects — so the tests changed rather than the component. Both now assert on the `datetime` attribute, which is locale-independent, and check only that the visible text is *not* the raw instant. | Nothing. Recorded because the failure looks like a bug in the code and is a bug in the test, and the next person to add a date assertion will otherwise write the same one. |
| M44 | **The evaluation cannot measure this change at all.** 21 of the 28 golden species have no curated care profile — *Aloe vera*, *Calathea orbifolia*, *Coffea arabica*, *Zamioculcas zamiifolia* and seventeen others — so in production they would all now get a researched baseline. The harness is wired to the curated tier only, so they get nothing, exactly as before. The change's entire benefit is invisible to every number in `eval/REPORT.md`. | The wiring is right and the consequence is the cost of it. Research inside the harness would put a web search and a model call inside a measurement, and reading the shared cache would make a score depend on which species previous runs happened to research first — both make the numbers mean less than they do now. Recording the blind spot is better than buying a noisy number with it. | Warm the cache deliberately: research the 21 species once, commit the resulting rows as a fixture, and wire the harness to the *stored* tier with research still off. The measurement is then reproducible and does measure the baseline's effect. That is its own change, and it should happen before anybody claims this one improved anything. |
| M45 | **The care-profile cache is shared, so one owner's run writes what every other owner reads.** Nothing personal crosses that boundary — a species name and public care guidance — but the write is triggered by whoever first photographs an unusual plant, and everybody afterwards reads it. A profile poisoned through a hostile search result would be poisoned for all of them. | The alternative is researching *Ocimum africanum* again for every account that photographs one, which is the cost the cache exists to avoid. The defences are the refusal gate and the untrusted fencing, which is why both are spec requirements rather than implementation details, and why the fencing tests were rewritten when a deliberate break showed two of them could not detect its removal. | If it ever matters: keep the shared row as the default and let an owner-scoped override shadow it, which is the shape the learned owner profile already has. Nothing today asks for that. |
| M46 | **`Deps.care_profile` changed its return type and the port-arity test cannot see it.** `tests/unit/agent/test_port_arity.py` was written after `weather` gained a fourth argument and both real wirings silently kept three-argument lambdas. It checks arity. This change alters what `care_profile` *returns* — an origin and sources that two surfaces read — without touching its signature, so the same class of silent breakage was available again through a hole in the test written to prevent it. | Covered by `tests/unit/agent/test_care_wiring.py`, which drives the real `build_deps` and asserts on a **researched** profile rather than the curated one that would pass whatever the tiers behind it did — and reads the harness's `Deps(...)` call from source. Reverting both wirings to the old shape fails six of its tests. | Generalising the arity test to compare return types is possible but weak: a `Callable[..., CareProfile]` annotation cannot express "and the origin must be set". The durable answer is what is done here — for each port, one test that exercises the real wiring for the case that actually differs. |
| M42 | **The evaluation's four outdoor cases now score against whatever the weather actually did.** They carry `location_text: "Berlin"` and no capture date, so the weather window anchors on the day the harness runs — two runs a week apart see different weather and therefore different prompts. This was already true when the weather was five aggregate numbers; the dated series makes it visible rather than making it new, and `answer_relevancy` and faithfulness on those four now vary with the sky. | Carried because fixing it means editing four fixtures and the change had no run to compare against anyway (see `M39` and `eval/REPORT.md`). Recording it now is the point: a future run that shows those four moving must not have the movement attributed to a code change. | Pin a `captured_at` into the four outdoor fixtures before the next run is treated as a baseline. The window then anchors on a fixed date and Open-Meteo's archive answers the same thing every time. |
| M43 | **A stale server can serve last week's schema, and nothing says so.** Found twice in one day: a `uvicorn --reload` process on port 8000 kept answering with a `DiagnosisOut` that had no `weather` field long after the file defining it had changed, and a second one earlier in the same session returned 422 for a route whose signature had moved. In both cases every test passed and the browser was simply wrong. The second time, the process could not be stopped at all — its PID had gone from the process table while the socket kept serving. | Not a defect in the application, which is why it is here rather than fixed: it is a property of a long-lived dev server on Windows. It is recorded because it cost two debugging detours, and because the failure looks exactly like a code bug from the client side. | Verify against a freshly started server on a spare port when a schema change is what you are checking — that is what caught it. A `/api/v1/health` payload carrying a build or schema hash would turn this into something a client could notice, and is cheap. |
| M41 | **Reverse geocoding was verified against the live service once, on 2026-08-27.** Three responses recorded — a city, a rural county, and a position in the North Sea — and every parsing test is built from them. The third is why recording matters: a position with nothing at it answers HTTP **200** with `{"error": "Unable to geocode"}`, which no amount of imagining would have produced. What the recordings do not cover: a rate-limited response under real load, a place whose most specific name is in a script the interface renders badly, and whatever the response gains in a future version. | The same position `M35` records for Pl@ntNet, and the same answer: one recording is a large improvement on none, and the adapter treats an unrecognised response as a failure like any other, so a shape that changes underneath this costs a place name rather than an upload. | Record another fixture the first time the parser drops something — it logs. The service reports no version, so there is no signal to watch for other than the log. |

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

### The Postgres migration (2026-08-25)

Everything moved into one database: domain records, photographs, and both graph
checkpointers. The corpus moved too and is not used — see `M25`.

**Three limitations closed, and one of them was closed by a test rather than by a fix.**
`M15` (~100 MB of checkpoint blobs per diagnosis) is gone because `ImageRef` carries a
key; `tests/unit/agent/test_state_size.py` asserts the property with a realistic 4 MB
image rather than describing it. `M3`'s dead `PARSE_DECLTYPES` left with the sqlite3
driver, and a schema test now fails on any timestamp column declared without a timezone.
`M17`'s stated blocker — that adding a column would require the project's first
migration — expired the moment Alembic arrived.

**What the work found that review had not.** Ownership was the point of the migration,
and three specific holes turned up while implementing it rather than while designing it:

- A thread id was `recheck-{plant_id}-{diagnosis_id}-{attempt}` — three values a second
  user could plausibly obtain, and the handle resumes a paused diagnosis that has already
  been paid for and is holding somebody's photographs. Handles now carry their owner and
  every resume path checks.
- `profile_service` filtered chat turns with `m.id > cursor or 0`, an integer comparison
  against a sentinel no UUID can have; and message ordering leaned on `id` being
  chronological, which an autoincrementing integer guaranteed and UUIDv7 only guarantees
  to the millisecond. A batch of turns written in one transaction shares a single clock
  reading, so a timestamp cursor skipped whole batches. The cursor is now a
  `(created_at, id)` position compared as a row value. **A test caught this, not review.**
- The My Plants card still read photographs from the uploads directory after they had
  moved into the blob store, so every card would have shown a placeholder. The tests did
  not catch it because they wrote real files to a temp directory that the component then
  found — they were testing the filesystem rather than the application's storage.

**One measurement worth carrying forward.** Building a retrieval parity gate turned up
`M24`: the embedding provider does not reproduce its own vectors. That is why the
retrieval move is deferred, and it also means an evaluation run is not perfectly
reproducible even at temperature 0 — a second source of variation alongside the model,
worth remembering before reading a small change in `eval/REPORT.md` as a real one.


### What a photograph knows about itself (2026-08-31)

Two things a photograph already carries, one of which the system was getting silently wrong.
An observation was dated by its upload, and the weather window anchored on that date — so a
plant photographed on Sunday and uploaded on Wednesday was diagnosed against three days it
never lived through, with nothing to notice, because by then the two dates are
indistinguishable.

**The privacy property is the interesting part, and the first version of it was incomplete.**
Coarsening a position to eleven kilometres before writing it to `observations` protects the
*column*. It does nothing about the precise fix still sitting in the uploaded file — and that
file is stored too. `upright_bytes` re-saves a photograph that needs turning, which
incidentally drops its metadata, so a portrait photograph out of a phone was fine; an upright
one is returned untouched, and every landscape photograph is upright. Roughly half of uploads
would have kept a doorstep on disk beside a row reading "near Frankfurt".

Found by asking what happens to the file rather than the column, before a photograph with a
real position was uploaded to it rather than after. The fix cuts the metadata segments out at
the byte level rather than re-encoding around them: a hash of a real phone photograph showed
that re-saving through Pillow, even at identical quantisation tables, does not return the
pixels that went in — and `store_upload` promises the model sees what the owner uploaded. A
privacy fix is not a licence to quietly resample it.

**Three ordering constraints, each of which is one line and reversible by accident.** Metadata
is read before normalisation, because the normalisation destroys it. The position is stripped
after the turn has been applied, because the tag saying which way to turn lives in the block
being stripped. And the strip happens before storage rather than after. The first has a test
that fails when the two calls are swapped — and only one test does, the one using a
photograph that needed turning, because an upright photograph is never re-saved and reading
afterwards appears to work perfectly. Every photograph out of a phone carries an orientation,
which makes the case that catches this the ordinary one and the case that hides it the
exception. That is the reverse of how it looks while writing the test.

**Verified live on 2026-08-31** with a photograph taken that morning in Frankfurt: the date
reached the field, the position resolved to a real place name, the stored position read 50.1
by 8.7 — eleven kilometres — and the stored photograph declared neither.

**The flow moved as a consequence, and two required fields disappeared from the first
screen.** Nobody is asked where the plant is before a run starts, because the photograph
usually knows and asking somebody to type what the file already says is asking them to do the
machine's work. Nobody is asked to name the plant either: somebody arriving with a sick plant
is asking what it is, and requiring a name first asks them to name the thing they came here to
have named. Both moved to where they can be answered well — the location to the pause,
prefilled; the name to the plant's own page, after the identification has proposed one.

**Which turned up a regression in the cap, and a better rule.** With four always-asked
questions and a default maximum of four, the agent's own questions were evicted entirely —
and those are the ones that discriminate in the specific case rather than in general. The cap
now governs what the agent thinks of rather than the whole list, which is what somebody
setting "at most four clarifying questions" is trying to bound.


### A second opinion on the species (2026-08-26)

Every diagnosis rests on the species, and until this change it came from one general-purpose
vision model asked "what is this?" — a guess nothing in the system could check. Pl@ntNet's
classifier is now a second, independent answer, and where the two disagree the owner settles
it at the pause that already existed.

**The two decisions worth carrying forward are both about independence.**

Neither method is told what the owner thinks. That reversed an existing behaviour — the
vision call used to be handed the owner's name for the plant as a hint — and the test
asserting the hint *was* sent now asserts it is not. The subtler half was the nickname:
`plant_name` is not a species field and "Kitchen basil" contains the species anyway. Without
this, agreement between the owner, the vision model and the classifier would be one claim
counted three times.

And what leads is never the higher confidence. The two methods report on scales that were
never calibrated against each other (`M37`), so the order is what the owner typed, then what
both agree on, then the vision model's — a rule about provenance rather than about numbers.

**Verified live on 2026-08-26**, against the real service with a real key, twice. With the
key: the vision model and Pl@ntNet independently agreed on *Monstera deliciosa*, and the two
candidates below it were both called "Mini monstera" and were different plants —
*Rhaphidophora tetrasperma* and *Monstera minima*. That collision is precisely why agreement
between methods is decided on the scientific name, and it turned up in the first real run
rather than in a test somebody imagined. Overriding the leader with the classifier's answer
carried through to the differential and was stored as `species_method=plantnet`,
`species_confirmed=true`, for $0.026. With the key removed: no choice offered, no attribution
shown, the run completed on the vision model's identification alone and recorded
`species_method=vision`, for $0.022.

**One real break, found by the task that exists to find it.** `eval/run_eval.py` builds
`Deps` by hand rather than through `agent.wiring.build_deps`, so a new required dependency
reached the application and not the harness: `uv run python -m eval.run_eval` would have
raised on its next run. Nothing caught it — the harness is excluded from coverage (`M1`) and
its own tests drive `run_case` with fixtures rather than `run_eval`'s wiring, so the only
detector was running a command that costs money and minutes.
`tests/unit/eval/test_harness_wiring.py` now compares the two by name, in both directions.

Also of note: the request shape was verified against the live service before any test was
written from it, which is `U2`'s lesson applied rather than repeated. Two readings of
Pl@ntNet's own documentation disagreed about whether `habit` is an accepted organ; the
service settled it. The same call established that an organ outside the vocabulary fails the
*whole request* with a 400 rather than being ignored — so one wrong value in `WIRE_ORGANS`
would have disabled identification silently and for ever, which is now handled by retrying
once without organs.


### The React frontend, and what a green suite was not saying (2026-08-26)

Streamlit was retired with the auth change; this is what replaced it. The interesting part
of the record is not the screens — it is that **the component suite passed, three times, while
describing screens that did not work.** Each was found within seconds of opening a browser,
and each is now covered by something that runs.

1. **The SSE parser yielded nothing.** The server sends CRLF and the parser split on two line
   feeds, so no frame boundary was ever found — for every event, silently. Eight unit tests
   passed because the fixtures had been written with bare line feeds. Found by watching the
   browser reconnect thirty-five times.
2. **Registration flushed and never committed.** Twenty-three tests passed because a flush and
   a commit are indistinguishable inside a transaction that is rolled back. Found by walking
   the README against a live server; now covered by `tests/unit/identity/test_write_boundaries.py`,
   which counts commits.
3. **Every clarifying question was an unlabelled text box.** The client's `Question` said
   `prompt` where the graph says `text` and omitted `kind` entirely, so the drainage question —
   four fixed options the graph reasons over — arrived as free text. The component fixtures had
   been written from the client's interface rather than from the graph's, so they agreed with the
   bug. These travel in a stream event, the one shape on the wire with no OpenAPI schema behind
   it, which is why `test_client_types.py` could not see it; `test_question_shape_agrees.py` now
   compares the two directly.

**The response was a class of test rather than three fixes.** Four files now check that two
sides which cannot import each other still agree: `test_client_types.py` (every interface
against the OpenAPI document), `test_source_names_agree.py` (the same word for a lookup on both
sides), `test_message_links.py` (an emailed link resolving to a route that exists), and
`test_question_shape_agrees.py`. All four run inside the Python gate and read TypeScript source.

**Two defects were only ever visible in a browser**, and are the reason the Playwright harness
exists rather than being a nicety on top of it. Startup requested `/auth/refresh` directly
instead of through the serialised `renew`, so StrictMode's double effect sent two; the second
replayed a rotated token, the server correctly revoked the family, and the *next* reload signed
the person out. A mocked refresh endpoint has no rotation to replay, so nothing in jsdom could
reproduce it — a unit test was written for it, found to pass against the bug, and deleted rather
than kept as a test that cannot fail. The other: a run creates a plant, and the grid had been
fetched before it existed, so finishing a first diagnosis and clicking home said "Nothing here
yet" about a plant that was really there.

The component suite now mounts in `StrictMode`, as `main.tsx` does. Mounting a tree the
application never mounts is how the renewal bug survived.

**The Python suite could hang rather than fail, and coverage made it certain.** Three stream
tests published their events from a thread that slept a fixed fifty milliseconds first — a bet
that the client had connected by then. Under `--cov`, which instruments every line and slows
everything, the bet loses: the events go to nobody, and the reader waits for events that have
already happened. The reader's own deadline could not save it, because the deadline was
checked between lines of a loop blocked *on* a line that never came — an eight-second bound
that bounded nothing, in the exact case it was written for.

The tests now wait for the subscription rather than sleeping towards it, and the reader closes
its response from a timer, so a lost event fails in eight seconds and says which event. The
gated suite went from hanging indefinitely to 1,606 tests in 2½ minutes. Worth recording
because the failure looked like slowness and was diagnosed as slowness twice before it was
looked at properly: a suite that hangs has told you *less* than one that fails, and the
temptation is to wait a bit longer rather than ask why.

**Accessibility was checked, and the check has a hole in it** — see `M32`. axe runs over every
route as a failure rather than a warning, and it found nothing, which is the expected result of
a checker and not evidence of a usable screen; the judgements a checker cannot make are tested
one at a time beside it. But it runs in jsdom, which computes no styles, so colour contrast is
skipped rather than checked. It was verified once in a real browser, on this date, and that is a
thing somebody did rather than a thing that runs.

It found two real defects: the evaluation screen kept its heading inside the branch that
succeeds, so the state a member always sees had no `h1` at all — the heading check had only ever
looked at one screen — and the differential took no focus when it replaced the reasoning panel,
after a wait long enough that somebody will have gone elsewhere.


## Two plan defects caught during implementation

Worth recording because the review loop, not the tests, is what caught them.

1. **LangGraph replays a node body from the top on resume.** The plan put clarifying-question selection *inside* `gather_context`, before `interrupt()` — so the question-selection model call would have fired a second time on every resume, in production as well as in tests. Fixed by splitting `select_questions` into its own node, which checkpoints before the interrupt-only node runs.
2. **The plan's `role-injection` regex made one of its own tests unsatisfiable.** The line-anchored pattern could not match `system:` appearing mid-line, which the plan's own multi-pattern test required. Relaxed to word-boundary matching, accepted for a detector whose output is logging rather than blocking.
