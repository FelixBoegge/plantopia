# pgvector Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pgvector the only retrieval path, remove Chroma and its two dependencies, and delete the cross-modal image path that no reachable model can supply.

**Architecture:** The embedding model does not change, so every vector stays identical and no evaluation baseline is needed. `PgVectorRetriever` already implements the same Protocol as `ChromaRetriever`, so wiring is construction rather than a rewrite — and because it holds a `Session`, the process-wide `lru_cache` around the retriever must go, which is a correctness fix as much as a simplification.

**Tech Stack:** Python 3.12, uv, PostgreSQL 17 + pgvector, SQLAlchemy 2.0, LangChain/LangGraph, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-pgvector-retrieval-design.md`

## Global Constraints

- **The embedding model stays `openai/text-embedding-3-small`.** 1536 dimensions. No Alembic migration, no new eval baseline.
- **Do not run `python -m eval.run_eval`.** It costs about $1.55 and is not warranted by a change that keeps every vector identical. The standing baseline is the 2026-08-19 run: 89.3% top-1, 96.4% top-3.
- **Tests make no LLM calls, ever.** Embedding calls in tests are mocked or use `tests/fakes/embeddings.py`.
- **`docker compose up -d db` is a prerequisite** for `uv run pytest` (`M26`).
- **Coverage gate: 85%.** This change deletes a large tested module *and* its tests — check the reported figure, never assume.
- **Lint:** `uv run ruff check .` and `uv run ruff format .`, line length 100.
- **The wipe happens before Task 2.** `corpus_chunks` shares one `database_url` with the user data, so a wipe takes the corpus with it.
- **Commit style:** conventional commits, lowercase subject, body explains why. Sign off with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Correct the references that outlived the deleted parity gate

Done first so the rest of the change is read against accurate documentation.

**Files:**
- Modify: `pyproject.toml:66-75`
- Modify: `knowledge/ingest_corpus.py:1-20`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Confirm both files are genuinely absent**

```bash
ls knowledge/export_chroma.py eval/capture_retrieval_fixtures.py 2>&1
git log --oneline --diff-filter=D -- knowledge/export_chroma.py eval/capture_retrieval_fixtures.py
```

Expected: both missing; `ddcea71` named as the commit that deleted them.

- [ ] **Step 2: Remove the two dead coverage omits**

In `pyproject.toml`, delete the `"knowledge/export_chroma.py"` and `"eval/capture_retrieval_fixtures.py"` entries **and** the comment paragraph above them that explains why they were omitted (lines ~66-75, the one beginning "One-shot migration tools, on the same precedent"). It argues about files that no longer exist. Leave the `eval/run_eval.py` omit and its own comment untouched.

- [ ] **Step 3: Correct `ingest_corpus.py`'s docstring**

Its final paragraph currently claims the opposite of what the code does:

> Makes no model calls. The vectors come from ``knowledge.export_chroma``, which is the whole reason the parity gate can compare exactly rather than approximately.

The function directly beneath it calls `embeddings.embed_documents(texts)`. Replace that paragraph with:

```
**This makes model calls.** One embedding request per batch, for 301 sections — about
$0.0005. It embeds the corpus itself rather than copying vectors from anywhere else; the
export that once seeded them from Chroma, and the parity gate it fed, were deleted in
``ddcea71``.
```

Also correct the paragraph above it: "Nothing reads this table yet: retrieval still runs on Chroma" is about to stop being true. Leave it for now — Task 4 removes it, and editing it twice invites a conflict. Note that in the commit body.

- [ ] **Step 4: Verify coverage still resolves**

```bash
uv run pytest 2>&1 | tail -5
```

Expected: PASS. Coverage is unaffected — omitting a nonexistent file was already a no-op — so the reported percentage should not move at all. If it does, something else changed and you should stop and find out what.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml knowledge/ingest_corpus.py
git commit -m "$(cat <<'EOF'
docs: stop crediting a deleted module for vectors ingest_corpus embeds itself

ingest_corpus's docstring claimed it makes no model calls and takes its
vectors from knowledge.export_chroma. The function directly beneath it calls
embeddings.embed_documents, and export_chroma was deleted in ddcea71 along
with the parity fixtures it fed. The command has been able to embed the corpus
by itself the whole time; only its documentation said otherwise, which is why
the retrieval move looked larger than it is.

pyproject also still omitted that file and capture_retrieval_fixtures.py from
coverage, with a paragraph arguing why -- for two files that are not in the
repository.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Populate `corpus_chunks`

Not a code change — an operational step, recorded as a task because the rest depends on it and because it must follow the wipe.

**Files:** none.

- [ ] **Step 1: Confirm the wipe has happened and the schema is current**

```bash
docker compose up -d db
uv run alembic upgrade head
uv run alembic check
```

Expected: `alembic check` reports no pending changes.

- [ ] **Step 2: Confirm the corpus table is empty or absent**

```bash
docker compose exec db psql -U plantopia -d plantopia -c "select count(*) from corpus_chunks;"
```

Expected: `0` after a wipe. If it returns 301, the corpus is already loaded — re-running is still safe (the upsert is keyed on `(doc_id, section)`), so continue.

- [ ] **Step 3: Ingest**

```bash
uv run python -m knowledge.ingest_corpus
```

Expected output: `loaded 301 chunks across 43 documents`. Costs about $0.0005. **This makes a real embedding call** — it is the one step in this plan that does.

- [ ] **Step 4: Verify what landed**

```bash
docker compose exec db psql -U plantopia -d plantopia -c \
  "select count(*) as chunks, count(distinct doc_id) as docs, vector_dims(embedding) as dims from corpus_chunks group by dims;"
```

Expected: `301 | 43 | 1536`. A different `dims` means the configured model changed and the plan's premise is broken — stop.

- [ ] **Step 5: No commit**

Nothing changed in the repository. Record the row counts; Task 6's register entry cites them.

---

### Task 3: Compare the two retrievers, while both still exist

The check that licenses the deletion. It must run before Chroma goes.

**Files:**
- Create: `tests/integration/test_retriever_parity.py`

**Interfaces:**
- Consumes: `PgVectorRetriever(session, embeddings)`, `ChromaRetriever(vectorstore, image_embedder)`.
- Produces: nothing. The test is deleted in Task 5.

- [ ] **Step 1: Write the comparison**

```python
"""Do the two retrievers answer the same question the same way?

Temporary, and deliberately so: it exists to license deleting Chroma and is removed with
it. Keeping a test of a store that no longer exists is how the `ui/components` citations
happened.

Both stores hold vectors from the same model, so the passages should match. What they
cannot be held to is the last bit: the provider does not reproduce its own vectors (`M24`
— 38 of 87 query strings embedded differently on a second call, moving merged scores by up
to 1.1e-3), and Chroma normalises in float32 and compares by inner product while
pgvector's `<=>` is cosine distance. So this asserts the passage *set* and the leading
ranks, and reports a tail difference rather than failing on one.
"""

import pytest

from eval.cases import load_cases

pytestmark = pytest.mark.integration

K = 6
STABLE_RANKS = 5


def _queries() -> list[str]:
    """The golden set's symptom text: the queries retrieval actually sees."""
    return [case.symptoms_text for case in load_cases()]


def test_both_retrievers_return_the_same_passages(chroma_retriever, pgvector_retriever):
    differences = []

    for query in _queries():
        chroma = chroma_retriever.search([query], k=K)
        pg = pgvector_retriever.search([query], k=K)

        keyed_chroma = [(p.doc_id, p.section) for p in chroma]
        keyed_pg = [(p.doc_id, p.section) for p in pg]

        assert set(keyed_chroma) == set(keyed_pg), (
            f"different passage sets for {query!r}:\n"
            f"  chroma: {keyed_chroma}\n  pgvector: {keyed_pg}"
        )
        assert keyed_chroma[0] == keyed_pg[0], (
            f"the leading passage differs for {query!r}: "
            f"{keyed_chroma[0]} vs {keyed_pg[0]} — this is a real finding, not drift"
        )
        assert keyed_chroma[:STABLE_RANKS] == keyed_pg[:STABLE_RANKS], (
            f"ranks 1-{STABLE_RANKS} differ for {query!r}"
        )

        if keyed_chroma != keyed_pg:
            differences.append((query, keyed_chroma[-1], keyed_pg[-1]))

    # Reported, not failed: a rank-6 swap between two candidates a thousandth apart is
    # M24's drift, not a regression.
    if differences:
        print(f"\n{len(differences)} of {len(_queries())} queries differ at rank {K}:")
        for query, chroma_tail, pg_tail = differences:
            print(f"  {query[:60]!r}: {chroma_tail} vs {pg_tail}")


def test_scores_agree_to_within_the_providers_own_drift(chroma_retriever, pgvector_retriever):
    """The two score definitions are the same definition. M24 bounds how close they get."""
    for query in _queries()[:5]:
        chroma = {(p.doc_id, p.section): p.score for p in chroma_retriever.search([query], k=K)}
        for passage in pgvector_retriever.search([query], k=K):
            counterpart = chroma.get((passage.doc_id, passage.section))
            if counterpart is not None:
                assert abs(passage.score - counterpart) < 0.01, (
                    f"{passage.doc_id}/{passage.section}: {passage.score} vs {counterpart} — "
                    "far above M24's measured 1.1e-3 drift, so the score definitions differ"
                )
```

Before writing this, read `eval/cases.py` for `load_cases`'s real signature and the field that holds a case's symptom text, and read `agent/schemas.py`'s `Passage` for its real attribute names. **Use what is there; do not assume `symptoms_text` or `doc_id` exist under those names.** Also read `tests/conftest.py` for the existing Chroma and pgvector fixtures — both suites already build these retrievers, so reuse those fixtures rather than adding new ones.

- [ ] **Step 2: Run it**

```bash
uv run pytest tests/integration/test_retriever_parity.py -v -m integration -s
```

Expected: PASS, with either no printed differences or a handful at rank 6.

- [ ] **Step 3: Judge the result — this is a gate, not a formality**

- **Passes, no differences:** proceed.
- **Passes with rank-6 differences:** proceed, and quote the count in Task 6's register entry.
- **A leading passage differs, or a score gap above 0.01:** **stop.** That is not drift. Report it and re-plan; the two stores are not equivalent and the switch is not safe.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_retriever_parity.py
git commit -m "$(cat <<'EOF'
test: compare Chroma and pgvector retrieval before removing either

Temporary by design, and removed with Chroma. It licenses the deletion in
place of an eval run, which is not warranted when every vector comes from the
same model and would cost $1.55 to tell us so.

Asserts the passage set and ranks 1-5, and reports a rank-6 difference rather
than failing: M24 measured the provider disagreeing with itself by up to
1.1e-3, and Chroma normalises in float32 while pgvector compares cosine
distance. A changed leading passage or a score gap above 0.01 is a real
finding and stops the change.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire `PgVectorRetriever` and drop the retriever cache

**Files:**
- Modify: `agent/wiring.py` — delete `_shared_retriever` (235-249) and `_retriever_for` (252-286), change `build_deps` (~159)
- Modify: `eval/run_eval.py:160-175`

**Interfaces:**
- Consumes: `PgVectorRetriever(session: Session, embeddings: Embeddings)` from `knowledge/pgvector_retriever.py`.
- Produces: `build_deps` unchanged in signature; `Deps.retriever` is now a `PgVectorRetriever`.

- [ ] **Step 1: Replace the construction in `agent/wiring.py`**

Delete `_shared_retriever` and `_retriever_for` entirely, along with the now-unused imports (`lru_cache` if nothing else uses it, `ChromaRetriever`, `build_vectorstore`, `load_corpus` if unused here, `ImageEmbedder`, `Path` if unused). In `build_deps`, replace `retriever = _shared_retriever(settings)` with:

```python
    # **Not cached, and it must not be.** The retriever holds this request's session, and a
    # process-wide cache is exactly where a session cannot live: it would pin one owner
    # into a process serving many, and a single SQLAlchemy session is not safe to share
    # across concurrent requests. There is nothing to cache anyway — the vectors are
    # already in Postgres, so construction loads no corpus and opens no collection.
    retriever = PgVectorRetriever(session, build_embeddings())
```

- [ ] **Step 2: Replace the construction in `eval/run_eval.py`**

Lines 160-175 build a `ChromaRetriever` inside a function. It has a session available (the harness opens one) — read the surrounding function and use it. Replace the body with `PgVectorRetriever(session, build_embeddings())` and delete the comment at line 173 about the image path having nothing to embed.

- [ ] **Step 3: Run the whole suite**

```bash
uv run pytest
```

Expected: failures **only** in tests that construct a `ChromaRetriever` directly or assert on the cache — `tests/unit/knowledge/test_retriever.py` (deleted in Task 5) and anything asserting `_retriever_for`'s caching. Fix tests that reach `build_deps` by passing a session; **do not** re-add a cache to make a test pass.

- [ ] **Step 4: Verify startup makes no embedding call**

```bash
uv run python -c "
from core.config import get_settings
from agent.wiring import build_deps, open_session
s = get_settings(); sess = open_session(s)
d = build_deps(s, session=sess)
print(type(d.retriever).__name__, len(d.retriever.known_doc_ids()))
"
```

Expected: `PgVectorRetriever 43`. This previously embedded 301 sections on the way to being ready; now it reads them.

- [ ] **Step 5: Re-run the parity test**

```bash
uv run pytest tests/integration/test_retriever_parity.py -v -m integration -s
```

Expected: still PASS. The wiring change must not have altered what pgvector returns.

- [ ] **Step 6: Commit**

```bash
git add agent/wiring.py eval/run_eval.py tests/
git commit -m "$(cat <<'EOF'
feat: retrieve from pgvector, and stop caching the retriever

The corpus has been in corpus_chunks and unread since 2026-08-25 (M25). It is
now the only retrieval path.

_shared_retriever and its six-scalar lru_cache go with Chroma, and their
removal is a correctness fix rather than a tidy-up: PgVectorRetriever holds a
Session, and a process-wide cache is precisely where a session must not live --
api/dependencies.py already argues this, that a cached service pins one owner
into a process serving many and a session is not safe to share concurrently.
There is also nothing left to cache, the vectors being in Postgres already.

Process start no longer embeds 301 sections to upsert them into Chroma, so it
touches no embedding endpoint at all.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Delete Chroma and the cross-modal path

The widest diff in the plan. One commit, because a half-removed retriever is not a state worth having.

**Files:**
- Delete: `knowledge/retriever.py`'s `ChromaRetriever` and `build_vectorstore`; `core/embeddings.py`; `tests/unit/knowledge/test_retriever.py`; `tests/unit/core/test_image_embedder.py`; `tests/integration/test_retriever_parity.py`
- Modify: `knowledge/retriever.py` — the `Retriever` Protocol (lines 29-66)
- Modify: `knowledge/pgvector_retriever.py:138-155`
- Modify: `agent/nodes/enrich.py:80-118`
- Modify: `core/config.py:42-56`, `core/llm.py:96-97`, `agent/studio.py:11` and `:53`, `data/models.py:391`
- Modify: `pyproject.toml` — drop `langchain-chroma` and `chromadb`
- Modify: `tests/conftest.py`, `tests/e2e/server.py`, `tests/fakes/embeddings.py`, `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: the `Retriever` Protocol loses `supports_image_search` and `search_by_image`.

- [ ] **Step 1: Delete the parity test**

```bash
git rm tests/integration/test_retriever_parity.py
```

It has done its job. Task 3's result is recorded in Task 6's register entry, which is where it belongs.

- [ ] **Step 2: Narrow the Protocol and delete `ChromaRetriever`**

In `knowledge/retriever.py`: remove `supports_image_search` and `search_by_image` from the `Retriever` Protocol, delete `build_vectorstore` and the whole `ChromaRetriever` class, and drop the `langchain_chroma` and `ImageEmbedder` imports. What remains is the Protocol and nothing else, so rewrite the module docstring — it currently opens "Chroma-backed retrieval over the disorder corpus."

```python
"""What the diagnosis graph needs from a retriever.

The Protocol only. The implementation is ``knowledge/pgvector_retriever.py``; this exists
so the nodes depend on the shape rather than the store, which is what let the store change
underneath them without a rewrite.
"""
```

If that leaves the file as a single Protocol of three members, consider whether it belongs in `agent/schemas.py` beside the types it returns — but **do not move it in this change**. A file move on top of this diff makes the deletion unreviewable.

- [ ] **Step 3: Delete the image path from `PgVectorRetriever`**

Remove `supports_image_search` and `search_by_image` (lines 138-155) and the `LoadedImage` import if now unused. Remove the `**No index.**`-adjacent docstring paragraph only if it mentions images; leave the rest of the module docstring, but delete its "Nothing uses this yet" opening paragraph (lines 3-7) — that is now false. Replace it with:

```
**The only retrieval path**, as of 2026-09-04. It shares the merge logic in
``knowledge.merging`` with nothing now, that being the last of it.
```

Check whether `knowledge/merging.py`'s docstring still claims to be shared between two implementations ("Extracted out of ``ChromaRetriever`` so the pgvector implementation can *share* it") — it does, at line 3. Correct it.

- [ ] **Step 4: Delete the visual-matches branch in `enrich.py`**

Remove the function containing lines 80-118 (the one guarded by `if not deps.retriever.supports_image_search`) and its call site, along with the `search_by_photograph` entry it appends to `tools_used` and the `LoadedImage` import if unused. Read the calling function first: the branch contributes to a list of passages, so the call site needs its contribution removed, not stubbed to `[]`.

- [ ] **Step 5: Delete the settings and the embedder**

```bash
git rm core/embeddings.py tests/unit/core/test_image_embedder.py tests/unit/knowledge/test_retriever.py
```

In `core/config.py`, delete `image_match_threshold` (line 44), `multimodal_embeddings` (56) and the whole comment block at 46-55 explaining why it is off. Keep `embedding_model` and its comment, trimming any clause about image input. Remove the corresponding assertions in `tests/unit/core/test_config.py` (lines ~77-86).

In `core/llm.py`, delete lines 96-97 pointing at `core.embeddings.ImageEmbedder`.

In `tests/fakes/embeddings.py`, remove `embed_image` (line 44) and correct the docstring at line 22 that advertises it.

- [ ] **Step 6: Remove `settings.chroma_path`, the dependencies and the ignores**

- `core/config.py:101` — delete `chroma_path`.
- `pyproject.toml` — remove `"langchain-chroma>=1.1.0"` and `"chromadb>=1.5.9"`, then `uv lock`.
- `.gitignore` — remove `data/chroma/`, `tests/e2e/.chroma/`, and `data/corpus_vectors.json` with its comment paragraph.
- `tests/conftest.py` and `tests/e2e/server.py` — remove the Chroma fixtures and setup. Read each: `tests/conftest.py:99` describes a fake that serves both the text and image interfaces, and that docstring needs correcting too.
- `agent/studio.py:11` and `:53`, and `data/models.py:391` — prose naming Chroma. `data/models.py:391` explains `sections_for`'s key "by reference to the Chroma ids it replaces"; reword to describe the key on its own terms.

```bash
rm -rf data/chroma tests/e2e/.chroma
```

- [ ] **Step 7: Confirm Chroma is gone**

```bash
grep -rn -i 'chroma' --include='*.py' --include='*.toml' --include='*.yml' . | grep -v -E '\.venv|__pycache__|uv\.lock|docs/plans|/archive/|known-limitations|superpowers/specs'
uv run python -c "import chromadb" 2>&1 | tail -1
```

Expected: no source hits; the import fails. `uv.lock` may retain transitive entries until `uv lock` runs — check it did.

- [ ] **Step 8: Full suite, twice**

```bash
uv run pytest
uv run pytest -m integration
```

Expected: PASS. Coverage will move — `ChromaRetriever` was substantial and tested, and both sides of the fraction just changed. **Confirm the gate holds; if it dips below 85%, do not lower the gate** — find what is now uncovered and either test it or record why not.

- [ ] **Step 9: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add -A
git commit -m "$(cat <<'EOF'
refactor!: remove Chroma, and the cross-modal path with it

The corpus lived in two places and only one was read (M25). pgvector is now
the only one, so ChromaRetriever, build_vectorstore, settings.chroma_path,
langchain-chroma and chromadb all go, along with the store on disk.

The cross-modal image path goes too, by decision rather than by consequence:
no multimodal embedding model will be available -- gemini-embedding-001 is
data-policy blocked on restricted keys and the OpenAI embedding models reject
image input -- so the idea is abandoned rather than parked. That removes a
Protocol member, a settings flag, a threshold, a branch in enrich, an HTTP
client and 91 lines of tests for a capability nothing can supply. It is the
one part of this change that removes a documented feature (design 10.4);
nothing observable changes, the flag having always been off.

knowledge/retriever.py is now the Protocol alone, which is what let the store
change underneath the nodes without a rewrite.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Record the change

**Files:**
- Modify: `docs/known-limitations.md`
- Modify: `README.md`, `docs/code-tour.md`, `openspec/config.yaml` (Chroma references)

- [ ] **Step 1: Strike `M25`**

Dated 2026-09-04. Record what it cost and what the comparison found — the row is more useful with Task 3's numbers in it than without: how many of the 28 queries returned identical passage sets, and how many differed at rank 6.

- [ ] **Step 2: Close `U2` as not pursued**

Not struck as fixed. The distinction matters: a future reader should find that the capability was considered and declined for a supply reason. Record that no multimodal embedding model is reachable, that the code is removed rather than dormant, and that `ImageEmbedder` went with it.

- [ ] **Step 3: Amend `M24`'s standing note**

`M24` says its finding "rules out any test that treats recorded embeddings as an exact baseline". Add that the parity fixtures it referred to were deleted in `ddcea71`, and that the Chroma/pgvector comparison this change ran instead asserted sets and leading ranks rather than exact vectors — so `M24` shaped the check that replaced them.

- [ ] **Step 4: Amend `M26` if the suite's prerequisites changed**

The suite still needs Postgres. If removing Chroma removed the *only* on-disk store the tests built, say so — it is one fewer thing a contributor must have working.

- [ ] **Step 5: Update the remaining current-state docs**

```bash
grep -rn -i 'chroma' README.md docs/code-tour.md openspec/config.yaml
```

`openspec/config.yaml` should already read "the corpus in pgvector" if Plan A's Task 6 ran; confirm rather than assume. For `README.md` and `docs/code-tour.md`, rewrite current-state claims and keep historical narration in the past tense. Do **not** touch `docs/plans/*`, `openspec/changes/archive/**` or the two course briefs.

- [ ] **Step 6: Verify every number**

The row you wrote cites 301 chunks, 43 documents, 1536 dimensions, $0.0005 and the comparison's counts. Each must be checkable from the repository or from Task 2's recorded output. Confirm before committing.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: strike M25, and close U2 as not pursued rather than fixed

M25 stood since 2026-08-25. Its row now carries what the switch cost and what
the Chroma/pgvector comparison found, which is worth more than the fact that
it closed.

U2 is closed as not pursued. It was never delivered and never will be: no
multimodal embedding model is reachable, so the code is removed rather than
left dormant. A future reader should find that it was declined for a supply
reason.

M24's note is amended to say that the fixtures it ruled out were already
deleted, and that it shaped the check that replaced them -- sets and leading
ranks rather than exact vectors.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage.** "What M25 was waiting for" → Task 1. "One variable" → Global Constraints (model fixed, no eval run). "The switch removes more than it adds" → Task 4. "The cross-modal path is dropped" → Task 5 Steps 3-5. "The data wipe" → Global Constraints and Task 2 Step 1. Sequence steps 1-7 → Tasks 1-6. Testing → Task 3, plus Task 5 Step 8. "Out of scope" (no index, no baseline, no model change) → Global Constraints.

**Ordering is load-bearing, not cosmetic.** Task 2 must follow the wipe or the corpus is ingested twice. Task 3 must precede Task 5 or there is nothing to compare against. Task 5 is one commit because a half-removed retriever is not a reviewable state.

**Type consistency.** `PgVectorRetriever(session, embeddings)` is used identically in Tasks 3 and 4. `Passage` attribute names are deliberately *not* asserted — Task 3 Step 1 instructs the implementer to read `agent/schemas.py` first, because guessing them here would plant a bug in a test.

**Known soft spots, flagged rather than hidden.** Task 3's fixtures are assumed to exist in `tests/conftest.py` for both stores; if only one does, the implementer builds the other from the existing pattern rather than inventing a new one. Task 5 Step 2 raises whether the bare Protocol should move to `agent/schemas.py` and explicitly defers it, because a move on top of this diff would make the deletion unreviewable. Task 5 Step 8's coverage outcome is genuinely unknown in advance — the instruction is to hold the gate, not to satisfy it by lowering it.
