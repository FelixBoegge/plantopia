# Known limitations and carried work

Phase 1 shipped with these known gaps. Each was raised during review, judged non-blocking,
and deliberately carried rather than silently dropped. They are recorded here so the next
person to touch this code — including future me — inherits the reasoning, not just the code.

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
| U7 | **Rejected and retake paths do not rotate `thread_id`.** State from the abandoned attempt stays in the checkpoint and merges into the retry. | Every field is overwritten by the re-run except `errors`, which accumulates harmlessly. | Rotate the thread id on those two paths as `_reset` already does. |
| U8 | **The upload-rejection message interpolates the model's description raw**, producing "This looks like A screenshot of a web form…., not a plant." — capitalised mid-sentence, with the description's own full stop left in. Seen on the first live run. | Cosmetic; the message is still comprehensible and the rejection itself is correct. | Lowercase the first character and strip trailing punctuation before interpolating, in the rejection copy. |

---

## Can affect a maintainer

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| M1 | **~~Coverage margin is ~5 statements wide.~~** *Largely resolved 2026-08-10.* It duly tripped on the next unrelated change (85.18%), so `ui/bootstrap.py` — real-infrastructure wiring with nothing unit-testable in it — was `omit`ted from `[tool.coverage.run]`, taking the total to 87.55%. `ui/pages/*` and `ui/components/*` still count in the denominator at a structural 0%, so the underlying shape remains. | Omitting genuinely untestable wiring is honest; omitting the page modules would hide real gaps, since they *are* measured under `-m ui`. | If it tightens again, fold the `ui` marker into the gated run rather than omitting more. |
| M2 | **The dose-detection regex misses spelled-out plural units.** `test_corpus_coverage.py` catches `5ml`, `2%`, `per litre`, but not "dilute 5 litres". | The corpus is hand-authored and reviewed, not generated; the abbreviated forms are the realistic risk. | Widen the pattern when the corpus stops being hand-authored. |
| M3 | **Two configuration lines are inert but read as guarantees.** `pyproject.toml`'s `filterwarnings` targets `plantopia.*`, which matches no module here (packages are `agent`, `core`, `tools`, …), so "error on our own DeprecationWarnings" is unenforced. `data/db.py`'s `PARSE_DECLTYPES` does nothing because every temporal column is declared `TEXT` and parsed by hand. | Both are harmless today and were specified in the plan. | Correct the regex to the real package names; drop `PARSE_DECLTYPES`. |
| M4 | **`retrieved` carries two score scales.** Tavily relevance scores are appended to a list of Chroma cosine scores. | This is *not* the §10.4 violation — that concerns text vs. image, which are kept strictly apart. The escalation gate has already fired by this point and nothing downstream ranks on the merged list, and the UI labels web provenance. | Normalise, or keep web results in a third field, if anything ever ranks `retrieved` again. |
| M5 | **`tools/weather.py` reads the wall clock** instead of an injected clock, unlike every other dated computation. | Harmless for a 21-day window; tests mock HTTP and never assert on dates. | Thread `Deps.now` through if the window ever becomes assertion-relevant. |
| M6 | **`tests/conftest.py` constructs `Settings(...)` which still honours `env_file=".env"`.** A developer with a local `.env` gets real thresholds bleeding into unit tests. | No `.env` is committed, so CI and a fresh clone are unaffected. | Pass `_env_file=None` in the fixture. |
| M7 | **Test-suite runtime grew from ~4s to ~34s**, almost entirely the parametrised corpus sweeps (six checks × 43 documents). | Still fast enough for a pre-commit loop. | `pytest-xdist` if it keeps growing. |
| M8 | **`store_upload` leaves orphan files** when a later upload in the same batch fails validation. | Disk litter only; no state references them. | Validate all, then write. |
| M9 | **Small coverage gaps in error paths:** the `RuntimeError` guard in `diagnosis_service`, `_escalation_query`'s output string, `invoke_structured`'s `method` passthrough, `tools_used` when a tool ran but returned nothing, `list_for_plant` multi-diagnosis ordering. | Each is a narrow branch whose behaviour is obvious from reading; none carries a safety property. | Add cases opportunistically when touching those files. |
| M10 | **`RoadmapRepository.mark()` on an unknown `step_id` silently no-ops** (no `rowcount` check). | No caller yet — it is the Phase 2 contract. | Check `cursor.rowcount` and raise when Phase 2 wires the UI. |
| M11 | **Repository read methods are unused in Phase 1** (`PlantRepository.get/delete`, the observation and diagnosis getters, most of the roadmap repository). | Deliberate forward work: they are the Phase 2 contract and are tested. | Nothing — Phase 2 consumes them. |
| M12 | **`token_usage_json` and `cost_usd` are never written at all.** The original entry here claimed the column was "populated but not read back"; the first live run showed both persist as `NULL`, so nothing populates them. | Phase 3's cost display is what needs them, and it will have to add the capture as well as the read. | Capture usage from the model response in `persist`, then add the `DiagnosisRecord` fields. |
| M13 | **`"Plantopia"` is hardcoded in the rejection copy** with no name constant. | One occurrence. | Extract if the product is ever renamed. |
| M15 | **The checkpoint database grows by ~100 MB per diagnosis.** `ImageRef.data_b64` puts whole images in graph state, and LangGraph re-serialises the entire state at every superstep. Measured on 2026-08-10: two completed diagnoses of 3 MB photographs produced 205 MB of checkpoint blobs (~6.4 MB × 29 rows) against a 69 KB main database. | Not noticed until the code tour, because no test uses a realistic image and the main database looks tiny. Nothing breaks — it is disk consumption, not corruption. | Drop `images` from state after its last consumer (`enrich`'s image path), or carry only `ref` and load bytes on demand. Downscaling uploads (U3) would cut it by roughly four on its own. Old threads can be deleted; nothing reads a checkpoint after its run completes. |
| M14 | **The corpus parser is permissive in two ways:** an empty section body reports as *missing* rather than *empty*, and duplicate headings in one document silently overwrite. | Neither can pass the coverage test, so a malformed document fails loudly at the suite rather than at runtime. | Distinguish the two error cases if corpus authoring is ever delegated. |

---

## Deliberate non-goals

Not limitations — decisions, recorded in [`PLAN.md`](../PLAN.md) §4.3 and §10.5.

- **No reference-image corpus.** Image-to-image matching would likely beat cross-modal text matching for visually distinctive disorders, but sourcing licensed photographs for 43 disorders is a larger content job than the text corpus, and public plant datasets skew heavily to crop leaf pathology while barely covering the watering, light and nutrient problems that dominate houseplant failures. Revisit once the evaluation harness can measure whether it actually helps.
- **No authentication, no product recommendations, no notifications, no community features.**
- **Phase 2 and Phase 3 scope** — plant profiles UI, the re-check flow, the chat agent, treatment feedback, LangSmith tracing, cost display, and the Ragas evaluation report — is planned, not missing.

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

## Two plan defects caught during implementation

Worth recording because the review loop, not the tests, is what caught them.

1. **LangGraph replays a node body from the top on resume.** The plan put clarifying-question selection *inside* `gather_context`, before `interrupt()` — so the question-selection model call would have fired a second time on every resume, in production as well as in tests. Fixed by splitting `select_questions` into its own node, which checkpoints before the interrupt-only node runs.
2. **The plan's `role-injection` regex made one of its own tests unsatisfiable.** The line-anchored pattern could not match `system:` appearing mid-line, which the plan's own multi-pattern test required. Relaxed to word-boundary matching, accepted for a detector whose output is logging rather than blocking.
