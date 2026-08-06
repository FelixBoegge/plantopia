# Known limitations and carried work

Phase 1 shipped with these known gaps. Each was raised during review, judged non-blocking,
and deliberately carried rather than silently dropped. They are recorded here so the next
person to touch this code — including future me — inherits the reasoning, not just the code.

Grouped by whether they can bite a user, a maintainer, or nobody yet.

---

## Can affect a user

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| U1 | **The live path has never run.** No part of this has executed against a real OpenRouter key — headless tests use scripted fakes throughout, by design. | The machine building it had no key. Every failure path degrades rather than crashes, so the blast radius is bounded. | Add a key to `.env` and run the wizard end to end. Verify the four model slugs in `core/config.py` still exist on OpenRouter. |
| U2 | **The multimodal embeddings request shape is unverified.** `core/embeddings.py` posts `{"input": [{"content": [{"type": "image_url", …}]}]}`, which is not the plain OpenAI `/embeddings` shape (`input: str \| list[str]`). | If it is wrong, `embed_image` returns `None`, `search_by_image` returns `[]`, and diagnosis proceeds on the text path alone — a silent loss of a feature, not a crash. | Check the current shape in OpenRouter's embeddings reference on the first live run. One method to adjust. |
| U3 | **Uploads are not re-encoded or downscaled.** Pillow is a dependency but unused; four 8 MB images go to the vision model at full size. | No correctness impact; cost only. | Downscale in `core/images.py:store_upload` before base64 encoding. |
| U4 | **An unanswered boolean question is recorded as "no".** `ui/pages/diagnose.py` conflates "no" with "didn't say". | Only the mandatory drainage question is a choice; boolean questions are model-generated and rare. | Use a tri-state widget or omit unanswered keys from the answers dict. |
| U5 | **The low-confidence banner omits the escalation advice** PLAN §13.4 specifies — it names the distinguishing tests but never suggests a local nursery or extension service. | The substantive half (tests to run) is present. | One sentence in `ui/components/differential.py`. |
| U6 | **`calcium-deficiency` omits blossom-end rot**, the most recognisable calcium symptom in fruiting plants. | The corpus deliberately skews houseplant/ornamental; the document is correct for that scope. | Add a section if the corpus ever grows toward edibles. |
| U7 | **Rejected and retake paths do not rotate `thread_id`.** State from the abandoned attempt stays in the checkpoint and merges into the retry. | Every field is overwritten by the re-run except `errors`, which accumulates harmlessly. | Rotate the thread id on those two paths as `_reset` already does. |

---

## Can affect a maintainer

| # | Limitation | Why it was carried | Fix if it matters |
|---|---|---|---|
| M1 | **Coverage margin is ~5 statements wide.** 85.42% against an 85% gate. `ui/pages/*` and `ui/components/*` count in the denominator but are only exercised under `-m ui --no-cov`, so they are structurally 0% in the gated run. Any growth in `ui/` can trip the gate on an unrelated change. | Not a correctness issue, and lowering the gate to hide it would be worse. | Either `omit` `ui/pages/*` from `[tool.coverage.run]` (they are measured separately) or fold the `ui` marker into the gated run. |
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
| M12 | **`token_usage_json` is write-only.** The column is populated but no `DiagnosisRecord` field reads it back. | Phase 3's cost display is what needs it. | Add the field when cost tracking lands. |
| M13 | **`"Plantopia"` is hardcoded in the rejection copy** with no name constant. | One occurrence. | Extract if the product is ever renamed. |
| M14 | **The corpus parser is permissive in two ways:** an empty section body reports as *missing* rather than *empty*, and duplicate headings in one document silently overwrite. | Neither can pass the coverage test, so a malformed document fails loudly at the suite rather than at runtime. | Distinguish the two error cases if corpus authoring is ever delegated. |

---

## Deliberate non-goals

Not limitations — decisions, recorded in [`PLAN.md`](../PLAN.md) §4.3 and §10.5.

- **No reference-image corpus.** Image-to-image matching would likely beat cross-modal text matching for visually distinctive disorders, but sourcing licensed photographs for 43 disorders is a larger content job than the text corpus, and public plant datasets skew heavily to crop leaf pathology while barely covering the watering, light and nutrient problems that dominate houseplant failures. Revisit once the evaluation harness can measure whether it actually helps.
- **No authentication, no product recommendations, no notifications, no community features.**
- **Phase 2 and Phase 3 scope** — plant profiles UI, the re-check flow, the chat agent, treatment feedback, LangSmith tracing, cost display, and the Ragas evaluation report — is planned, not missing.

---

## Two plan defects caught during implementation

Worth recording because the review loop, not the tests, is what caught them.

1. **LangGraph replays a node body from the top on resume.** The plan put clarifying-question selection *inside* `gather_context`, before `interrupt()` — so the question-selection model call would have fired a second time on every resume, in production as well as in tests. Fixed by splitting `select_questions` into its own node, which checkpoints before the interrupt-only node runs.
2. **The plan's `role-injection` regex made one of its own tests unsatisfiable.** The line-anchored pattern could not match `system:` appearing mid-line, which the plan's own multi-pattern test required. Relaxed to word-boundary matching, accepted for a detector whose output is logging rather than blocking.
