# Cleanup and Streamlit Purge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every live trace of the retired Streamlit UI, delete one dead function, close five small carried items, and flatten `api/errors.py`'s repeated handlers — without changing what the application does.

**Architecture:** Four independent lanes. Lanes 1 and 2 touch only comments, docstrings, configuration and one deletion, so the existing suite is the proof. Lane 3 contains the one behavioural change (upload downscaling) and one bug fix (the delete-plant redirect), both test-first. Lane 4 threads settings into the error handlers under existing tests.

**Tech Stack:** Python 3.12, uv, FastAPI, Pillow, pytest; React 19 + TypeScript, TanStack Query v5, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-04-cleanup-and-streamlit-purge-design.md`

## Global Constraints

- **Tests make no LLM calls, ever.** Models arrive via `core/llm.py` and are replaced with a scripted fake; HTTP is mocked with `respx`.
- **`docker compose up -d db` is a prerequisite** for `uv run pytest` (`M26`).
- **Coverage gate: 85%.** `addopts` includes `--cov --cov-fail-under=85`. Deletions move both sides of that fraction — check, never assume.
- **Lint:** `uv run ruff check .` and `uv run ruff format .`, line length 100.
- **Frontend:** `cd web && npx tsc -b && npm test`.
- **Do not touch Tier 3 historical records:** `docs/plans/*.md`, `docs/superpowers/specs/*.md`, `openspec/changes/archive/**`, `project_brief_*.md`. `docs/known-limitations.md` is edited *only* to strike resolved rows and add dated notes, never to remove the word "Streamlit" from existing prose.
- **Do not remove the `"8501" not in settings.app_url` assertion** in `tests/unit/identity/test_message_links.py`. It is a live guard.
- **Commit style:** conventional commits, lowercase subject, body explains why. Sign off with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- **Documentation is prose that argues,** not bullet lists that assert. Numbers in documents must be verifiable from the repository.

---

### Task 1: The delete-plant redirect

The one live user-facing bug in this plan. Do it first so it can ship independently of everything else.

**Files:**
- Modify: `web/src/api/hooks/plants.ts:44-51`
- Modify: `web/src/screens/plants/PlantDetail.tsx:107` and `:148`
- Test: `web/src/screens/plants/plants.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: `useRemovePlant(plantId: string)` — signature **changes** from `useRemovePlant()` with `mutate(plantId)` to `useRemovePlant(plantId)` with `mutate()`, matching `useRenamePlant(plantId)` and `useMarkStep(plantId)` directly above and below it.

- [ ] **Step 1: Write the failing test**

Add to `web/src/screens/plants/plants.test.tsx`. Follow the file's existing MSW and render helpers — read the top of the file first and reuse them rather than inventing new ones.

```tsx
it("returns to the plants overview after a plant is removed", async () => {
  // The detail query and the list query share a prefix, so a prefix invalidation
  // refetches the plant that was just deleted and renders its 404 over the redirect.
  server.use(
    http.delete("/api/v1/plants/p1", () => new HttpResponse(null, { status: 204 })),
    http.get("/api/v1/plants/p1", () => HttpResponse.json(plantDetail())),
    http.get("/api/v1/plants", () => HttpResponse.json([])),
  );

  renderAt("/plants/p1");

  await userEvent.click(await screen.findByRole("button", { name: /remove/i }));
  await userEvent.click(await screen.findByRole("button", { name: /yes, remove/i }));

  expect(await screen.findByRole("heading", { name: /your plants/i })).toBeVisible();
  expect(screen.queryByText(/this plant could not be loaded/i)).not.toBeInTheDocument();
});
```

Match the confirm-button's accessible name to what `PlantDetail.tsx` actually renders — read lines 136-160 and copy it. Reuse the file's existing `plantDetail()` fixture if it has one; if not, build the smallest object `usePlant` will accept.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd web && npx vitest run src/screens/plants/plants.test.tsx -t "returns to the plants overview"
```

Expected: FAIL — "this plant could not be loaded" is in the document, or the heading is never found.

- [ ] **Step 3: Fix the hook**

Replace `useRemovePlant` in `web/src/api/hooks/plants.ts`:

```ts
export function useRemovePlant(plantId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => request(`/plants/${plantId}`, { method: "DELETE" }),
    // **Exact, and not awaited.** `keys.plants` is a prefix of `keys.plant(id)`, so a
    // prefix invalidation also refetches the plant just deleted — which 404s, and a 404
    // is permanent, so it renders "This plant could not be loaded" instead of retrying.
    // Returning the promise made it worse: an onSuccess that returns one is awaited, so
    // the error rendered before the caller's navigate ran. `removeQueries` on the detail
    // key is not the fix either — the observer is still mounted, so it would refetch.
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: keys.plants, exact: true });
    },
  });
}
```

- [ ] **Step 4: Update the caller**

In `web/src/screens/plants/PlantDetail.tsx`, line 107:

```ts
  const remove = useRemovePlant(plantId);
```

and line 148 — `replace` so the back button cannot return to a plant that is gone:

```tsx
                remove.mutate(undefined, {
                  onSuccess: () => navigate("/", { replace: true }),
                })
```

`PlantSettings` receives `plantId` as a prop already, so nothing else moves.

- [ ] **Step 5: Run the test and the suite**

```bash
cd web && npx vitest run src/screens/plants/plants.test.tsx && npx tsc -b && npm test
```

Expected: the new test PASSES; `tsc` is clean; no other test regresses. If another test called `remove.mutate(plantId)`, update it to `remove.mutate(undefined, …)`.

- [ ] **Step 6: Commit**

```bash
git add web/src/api/hooks/plants.ts web/src/screens/plants/PlantDetail.tsx web/src/screens/plants/plants.test.tsx
git commit -m "$(cat <<'EOF'
fix: return to the plants list after removing a plant, instead of its 404

Removal already navigated. The error still won, because keys.plants is a
prefix of keys.plant(id): invalidating the list refetched the detail query of
the plant just deleted, which 404s without retrying, and rendered "This plant
could not be loaded". The onSuccess also returned the invalidation promise
rather than voiding it, and a returned promise is awaited -- so the error
rendered before navigate was reached.

Exact invalidation so the detail query is never matched, void so navigation is
not queued behind a refetch, and replace so back does not return to a plant
that no longer exists.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Downscale uploads before the vision model (U3)

**Files:**
- Modify: `core/config.py` (near `max_upload_bytes`, line ~227)
- Modify: `core/images.py` — `store_upload`, and a new `downscaled` function
- Test: `tests/unit/core/test_images.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `downscaled(data: bytes, *, max_edge: int) -> bytes`; `Settings.max_image_edge_px: int` (default `1568`).

- [ ] **Step 1: Add the setting**

In `core/config.py`, beside `max_upload_bytes`:

```python
    # **The long-edge cap applied to a stored photograph.** 1568 is the point beyond which
    # the major vision models downscale server side anyway, so pixels above it are paid for
    # and then discarded. A setting rather than a constant because every other limit
    # governing an upload is one, and a reviewer changing one should find them together.
    max_image_edge_px: int = Field(default=1568, gt=0)
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/core/test_images.py`. Read the file first and reuse its existing image-building helper; if it has none, add this one beside the tests.

```python
def _jpeg(width: int, height: int) -> bytes:
    """A JPEG of a given size. Content is irrelevant; only the dimensions are asserted."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), (10, 90, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_a_large_photograph_is_capped_on_its_long_edge():
    from io import BytesIO

    from PIL import Image

    from core.images import downscaled

    result = downscaled(_jpeg(4000, 3000), max_edge=1568)

    with Image.open(BytesIO(result)) as opened:
        assert max(opened.size) == 1568
        # Aspect ratio preserved: 4000x3000 is 4:3, so the short edge follows.
        assert opened.size == (1568, 1176)


def test_a_photograph_inside_the_cap_is_returned_untouched():
    """Byte-identical, not merely equivalent: no re-encode means no quality loss."""
    from core.images import downscaled

    original = _jpeg(800, 600)

    assert downscaled(original, max_edge=1568) is original


def test_a_portrait_photograph_is_capped_on_its_height():
    """The cap is on the long edge, whichever edge that is."""
    from io import BytesIO

    from PIL import Image

    from core.images import downscaled

    with Image.open(BytesIO(downscaled(_jpeg(1200, 4000), max_edge=1568))) as opened:
        assert opened.size == (470, 1568)


def test_undecodable_bytes_are_returned_unchanged():
    """Not this function's gate. `validate_upload` decides what counts as an image."""
    from core.images import downscaled

    assert downscaled(b"not an image", max_edge=1568) == b"not an image"
```

Then the ordering guard — the constraint most likely to be broken by this change:

```python
def test_metadata_is_still_read_from_the_bytes_as_they_arrived(blobs, settings, user_id):
    """Downscaling re-encodes, which destroys EXIF. It must run after `read_metadata`.

    Mirrors the existing orientation-ordering test: if downscaling moves ahead of the
    metadata read, a photograph lands with no capture date and the diagnosis silently
    loses the ability to say how old it is.
    """
    from core.images import store_upload

    stored = store_upload(
        _jpeg_with_capture_date(4000, 3000, "2026:08:10 10:50:48"),
        blobs=blobs,
        user_id=user_id,
        settings=settings,
    )

    assert stored.metadata.taken_at is not None
```

Build `_jpeg_with_capture_date` from the helper the existing metadata tests already use — check `tests/unit/core/test_metadata.py` for one and import or copy it rather than writing a third EXIF builder. Match `stored.metadata`'s real attribute name by reading `PhotographMetadata` in `core/metadata.py`.

- [ ] **Step 3: Run them to verify they fail**

```bash
uv run pytest tests/unit/core/test_images.py -v
```

Expected: FAIL — `ImportError: cannot import name 'downscaled'`.

- [ ] **Step 4: Implement `downscaled`**

Add to `core/images.py`, directly below `upright_bytes` (they are siblings — both normalise stored bytes):

```python
def downscaled(data: bytes, *, max_edge: int) -> bytes:
    """Cap an image's long edge, preserving its aspect ratio.

    Returns ``data`` unchanged when it already fits, so the common case costs no
    re-encode and loses no quality — the same bargain ``upright_bytes`` makes for a
    photograph that needs no turning.

    **Cost, not accuracy.** Four 8 MB photographs reach the vision model at full
    resolution today, and the models downscale above this edge themselves, so the pixels
    above it are billed and discarded. No measurement in this project can see the vision
    layer (``M19``), so this deliberately claims nothing about what the model concludes.

    Returns ``data`` unchanged when the bytes cannot be decoded: ``validate_upload`` is
    the gate on what counts as an image, and this is not the place to start rejecting
    uploads it let through.
    """
    try:
        with Image.open(BytesIO(data)) as opened:
            if max(opened.size) <= max_edge:
                return data
            image_format = opened.format
            # `thumbnail` caps the long edge and keeps the ratio, in place.
            copy = opened.copy()
            copy.thumbnail((max_edge, max_edge), Image.LANCZOS)
            buffer = BytesIO()
            copy.save(buffer, format=image_format, quality=95)
    except Exception:  # noqa: BLE001 — see the docstring: not this function's gate
        return data
    return buffer.getvalue()
```

- [ ] **Step 5: Call it from `store_upload`**

In `core/images.py`, immediately after the `upright_bytes` call and **before** `without_position`:

```python
    # After `read_metadata`, which needs the bytes as they arrived, and beside
    # `upright_bytes` for the same reason: both re-encode, and a re-encode is what
    # destroys the metadata block.
    data = downscaled(data, max_edge=settings.max_image_edge_px)
```

Then extend `store_upload`'s docstring — the existing one contains a **"No downscaling."** paragraph that is now false. Replace that paragraph with:

```
    **Downscaled to ``max_image_edge_px``.** Pillow applies the declared orientation and
    caps the long edge; nothing else. The cap is cost rather than accuracy — see
    ``downscaled`` — and it runs after the metadata read for the reason this module's
    docstring gives.
```

- [ ] **Step 6: Run the tests**

```bash
uv run pytest tests/unit/core/ -v && uv run pytest
```

Expected: all PASS, coverage gate holds. If the existing "no downscaling" test asserts bytes are unchanged for a large image, it encodes the old contract — update it to assert the *new* one and say so in the commit body.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff format core/ tests/ && uv run ruff check core/ tests/
git add core/config.py core/images.py tests/unit/core/test_images.py
git commit -m "$(cat <<'EOF'
feat: cap a stored photograph's long edge at 1568 pixels

max_upload_bytes is 8 MB and max_images_per_observation is 4, so a diagnosis
could send 32 MB to the vision model at full resolution -- above the edge the
models downscale to themselves, which means those pixels were billed and then
discarded.

Cost, not accuracy: M19 still stands, so no measurement here can see the
vision layer and this claims nothing about what the model concludes. An image
already inside the cap is returned unchanged, so the common case costs no
re-encode.

Ordered after read_metadata and beside upright_bytes, because both re-encode
and a re-encode is what destroys EXIF. A test asserts the capture date still
survives a downscaled upload.

Closes U3.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Three small copy and config items (U8, M13, M52)

**Files:**
- Modify: `agent/nodes/intake.py:52-58`
- Modify: `services/chat_events.py:39-45`, `api/errors.py:144` and `:177`
- Create: `web/.nvmrc`
- Modify: `web/package.json`
- Test: `tests/unit/agent/nodes/test_intake.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Copy and configuration only.

- [ ] **Step 1: Write the failing test for the rejection copy (U8)**

Add to `tests/unit/agent/nodes/test_intake.py`, reusing the file's existing node-invocation helper:

```python
def test_the_rejection_reads_as_one_sentence():
    """Seen live: "This looks like A screenshot of a web form…., not a plant."

    The model writes a standalone sentence — capitalised, full-stopped — and it is
    interpolated mid-sentence. Both ends need trimming, and the message must not end
    up with two full stops.
    """
    message = rejection_message("A screenshot of a web form.", app_title="Plantopia")

    assert message.startswith("This looks like a screenshot of a web form, not a plant.")
    assert "…." not in message
    assert "A screenshot" not in message
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/unit/agent/nodes/test_intake.py -v
```

Expected: FAIL — `rejection_message` is not defined.

- [ ] **Step 3: Extract and fix the copy**

In `agent/nodes/intake.py`, add above the node:

```python
def rejection_message(what_it_is: str, *, app_title: str) -> str:
    """The refusal shown when an upload is not a plant.

    The description comes from the model as a standalone sentence, and it is used here
    mid-sentence — so its capital and its full stop both have to go, or the result reads
    "This looks like A screenshot of a web form…., not a plant." (``U8``, seen live).
    """
    described = what_it_is.strip().rstrip(".")
    if described[:1].isupper() and not described[1:2].isupper():
        # Lowercased only when it looks like ordinary prose. "NASA logo" keeps its capitals.
        described = described[0].lower() + described[1:]
    return (
        f"This looks like {described}, not a plant. "
        f"{app_title} only diagnoses plants — please upload a photo of the plant "
        # keep the remainder of the existing sentence exactly as it is
    )
```

Read lines 52-58 first and carry the rest of the existing wording across verbatim; only the interpolation and the product name change. Then call it from the node, passing `deps.settings.app_title`.

- [ ] **Step 4: Route the other product names through the setting (M13)**

`services/chat_events.py` lines 39-45 hardcode `"Plantopia"`. Each becomes `settings.app_title`.

**`api/errors.py` is deliberately NOT in this task.** Its two occurrences are handled by
Task 7, which rewrites those exact lines and threads `settings` into `register`. Editing
them here as well would mean touching the file twice and colliding with that task.

Check how each site reaches settings before editing: `api/errors.py`'s handlers take `(request, exc)` and may have no settings to hand. **If a handler cannot reach settings without threading a new dependency through it, leave that occurrence alone** and note it in the commit body — `M13` is a naming tidy-up and is not worth a new dependency injection path. `core/config.py`'s own default stays a literal; it is the definition.

- [ ] **Step 5: Pin the Node version (M52)**

```bash
printf '22\n' > web/.nvmrc
```

Add to `web/package.json`, after `"type": "module"`:

```json
  "engines": {
    "node": ">=22"
  },
```

`.github/workflows/ci.yml:139` names Node 22; these must agree.

- [ ] **Step 6: Run everything**

```bash
uv run pytest && uv run ruff check . && cd web && npm ci --dry-run 2>&1 | tail -3 && npx tsc -b
```

Expected: tests pass; `engines` does not make the install fail.

- [ ] **Step 7: Commit**

```bash
git add agent/nodes/intake.py services/chat_events.py api/errors.py tests/unit/agent/nodes/test_intake.py web/.nvmrc web/package.json
git commit -m "$(cat <<'EOF'
fix: read the rejection as a sentence, name the product once, pin Node

Three carried items, none of which changes a flow.

U8: the model writes a standalone sentence and it was interpolated
mid-sentence, producing "This looks like A screenshot of a web form...., not a
plant." Its capital and its full stop are both trimmed, and a description that
is an acronym keeps its capitals.

M13: the register said one hardcoded "Plantopia" and there were six.
settings.app_title already existed; the user-facing ones now use it.

M52: CI named Node 22 and nothing else did, so a laptop and the machine could
disagree and the machine would be believed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Remove `recheck_thread` (M50)

**Files:**
- Modify: `agent/threads.py` — delete `recheck_thread` (lines 38-49), extend the module docstring
- Modify: `tests/unit/agent/test_threads.py` — remove the import and eight assertions

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. `agent.threads` loses one public name.

- [ ] **Step 1: Prove it has no production caller**

```bash
grep -rn 'recheck_thread' --include='*.py' . | grep -v -E '\.venv|__pycache__|/tests/'
```

Expected: only `agent/threads.py:38`, its definition. **If anything else appears, stop** — the premise is wrong and this task needs re-planning.

- [ ] **Step 2: Delete the function and keep its argument**

Remove `recheck_thread` from `agent/threads.py`. Its docstring carries the `U7` reasoning, which must survive — the module docstring already tells the first half. Extend that docstring's second paragraph to:

```
The previous scheme made that a real hazard: a re-check thread was
``recheck-{plant_id}-{diagnosis_id}-{attempt}``, built from three values a second user
could plausibly guess or enumerate, and the ``attempt`` suffix existed only to stop a
retry resuming an abandoned attempt's wreckage (``U7``). Every handle now carries the
owner, and every resume path checks it before touching state — and since no caller
derives a handle any more, a re-check simply gets a fresh random one like any other run.
```

- [ ] **Step 3: Remove its tests**

In `tests/unit/agent/test_threads.py`, remove `recheck_thread` from the import and delete the assertions that use it (lines ~41, 50, 56, 63, 72, 74). Several sit inside tests that also assert other things — **read each test whole and delete only the `recheck_thread` assertions**, keeping any test that still has a subject. Delete a test outright only when `recheck_thread` was its only subject.

- [ ] **Step 4: Run the suite and check coverage**

```bash
uv run pytest tests/unit/agent/test_threads.py -v && uv run pytest
```

Expected: all PASS. The gate is at 85% and this deletes tested lines *and* tests — confirm the reported total, do not assume it moved favourably.

- [ ] **Step 5: Commit**

```bash
git add agent/threads.py tests/unit/agent/test_threads.py
git commit -m "$(cat <<'EOF'
refactor: delete recheck_thread, which has had no caller since Streamlit

Every run now gets a fresh diagnosis_thread(user_id) with a random component,
initial or re-check alike, so the derived handle has been dead for the whole
life of the React frontend. Eight test assertions kept it green and invisible.

Its docstring carried the U7 collision story -- the derived
recheck-{plant_id}-{diagnosis_id}-{attempt} scheme, and why attempt existed --
and that is the argument for the current scheme, so it moves into the module
docstring rather than going with the function.

Closes M50.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Streamlit purge — live code and tests (Tier 1 and Tier 2)

**Files (all comment/docstring only):**
- Modify: `services/__init__.py:1`, `services/diagnosis_service.py:1`, `api/__init__.py:3`
- Modify: `api/dependencies.py:5`, `agent/wiring.py:4`, `agent/studio.py:5`
- Modify: `eval/run_eval.py:272`, `eval/metrics.py:232`, `eval/report.py:73`, `core/images.py:61`
- Modify: `tests/api/test_app_shape.py:71`, `tests/unit/eval/test_report.py:186`, `tests/unit/eval/test_metrics.py:400`
- Modify (Tier 2, reword): `tests/unit/identity/test_message_links.py`, `tests/e2e/mail.py:5`, `tests/unit/knowledge/test_retriever.py:181`, `web/e2e/people.ts:10`, `web/e2e/account.spec.ts:27`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. No executable line changes.

- [ ] **Step 1: Rewrite the three docstrings that describe a live Streamlit client**

`services/__init__.py` — one line, currently "The orchestration layer between the Streamlit UI and the diagnosis agent.":

```python
"""The orchestration layer between the HTTP API and the diagnosis agent."""
```

`services/diagnosis_service.py` — first line and the paragraph under it:

```python
"""The orchestration boundary between the API and the agent.

Its caller knows nothing about LangGraph, checkpointers, or resume commands. It calls
``start``, renders questions, calls ``answer``, and renders the result.
"""
```

`api/__init__.py` — "A second client of ``services/``, alongside Streamlit rather than instead of it." becomes:

```python
"""The HTTP interface.

The only client of ``services/``. Routers depend on services and never on repositories —
the one deliberate exception is serving a photograph, which needs the blob store because
no service owns image bytes.
"""
```

- [ ] **Step 2: Restate the four comparisons as rules**

Each currently explains itself by contrast with Streamlit. State the rule directly.

`api/dependencies.py:3-7`:

```python
**One session per request.** Opened when the request arrives, closed when the response is
done. Never cached process-wide, for two reasons: a cached service would pin one owner
into a process serving many, and a single SQLAlchemy session is not safe to share across
concurrent requests.
```

`agent/wiring.py:2-8` — drop the `ui/bootstrap.py` provenance and keep the argument:

```python
Wiring lives here rather than at an entry point because there is more than one: the API
process and the LangGraph dev server behind Studio, which builds the graph itself in a
plain Python process. The one thing worse than wiring in an awkward place is the same
wiring in two places, quietly drifting until Studio shows a graph the app does not run.
```

`agent/studio.py:5` — "Both factories build the same objects the Streamlit app does" becomes "Both factories build the same objects the API does".

`tests/api/test_app_shape.py:71` — docstring becomes:

```python
    """Never cached process-wide: a cached service would pin one owner into a process
    serving many, and a session is not safe to share concurrently."""
```

- [ ] **Step 3: Drop the six citations of deleted `ui/` files**

Each asserts a real rule and cites a file that no longer exists. Keep the rule, cut the citation.

- `eval/run_eval.py:272`: `# $0.00 (consistent with ui/components/cost_badge.py).` → `# $0.00, which would be a fabrication rather than a measurement.`
- `eval/metrics.py:230-232`: drop `(consistent with ``ui/components/cost_badge.py``)`, keep "never a fabricated ``$0.00``".
- `eval/report.py:72-74`: `matching ``ui/components/cost_badge.py``'s rule for the same data at the per-diagnosis scale.` → `the same rule the per-diagnosis figures follow.`
- `tests/unit/eval/test_report.py:186` and `tests/unit/eval/test_metrics.py:400`: drop `— consistent with ``ui/components/cost_badge.py``` from both docstrings.
- `core/images.py:59-62`: the comment says `exif_transpose` clears the tag so nothing turns the image twice, "including ui/components/plant_photo.py, which still needs to correct the photos uploaded before this function existed". Cut the clause from "including" onward; the first half is the reason and stands alone.

- [ ] **Step 4: Reword Tier 2 — the five sites where Streamlit names a past bug**

The lesson survives; the brand name goes. **The `"8501" not in settings.app_url` assertion does not move.**

`tests/unit/identity/test_message_links.py` module docstring:

```python
"""Every verification and reset message once pointed at `localhost:8501/verify` — the port
a retired UI served on, months after that UI was retired, and a path the web client has
never served. Nobody could have completed a registration through the interface, and a link
in an email is unfixable once sent. Nobody can be told the address was wrong.
"""
```

and the test at line 56: `"""The old default outlived the UI it pointed at by two changes, which is exactly how long the links were broken."""`. Leave the test's *name* alone — `test_the_default_address_is_not_a_service_that_was_retired` is already brand-free and accurate.

`tests/e2e/mail.py:5` — "this project has already shipped a verification link pointing at a retired Streamlit port" → "...pointing at a retired UI's port".

`web/e2e/people.ts:10` and `web/e2e/account.spec.ts:27` — "a retired Streamlit port" → "a retired UI's port".

`tests/unit/knowledge/test_retriever.py:181` — "every ``streamlit run`` re-indexed" → "every application start re-indexed". The mechanism is not UI-specific.

- [ ] **Step 5: Verify no executable line changed**

```bash
git diff -U0 -- '*.py' '*.ts' | grep -E '^\+' | grep -v -E '^\+\+\+' | grep -vE '^\+\s*(#|\*|"""|\'\'\'|//|$)' 
```

Expected: **no output**, or only lines that are visibly continuations of a docstring or comment. Any real statement here means the task overreached.

- [ ] **Step 6: Run both suites**

```bash
uv run pytest && uv run ruff check . && cd web && npx tsc -b && npm test
```

Expected: everything PASSES, unchanged. This is the proof the lane is inert.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: stop describing a Streamlit UI that was retired months ago

services/__init__.py said the layer orchestrates between the Streamlit UI and
the agent; api/__init__.py called the HTTP interface a second client alongside
Streamlit. Both described an architecture that has not existed for weeks, and
both are the first thing anybody reads on entering those packages.

Six further sites cited ui/components/cost_badge.py and plant_photo.py as
authorities for a rule. The rules are real and stay; the citations pointed at
files that are not in the repository.

Where the name recorded a past bug rather than a present architecture, it is
reworded rather than erased -- the emailed links that pointed at a retired
port, and the re-indexing that duplicated the corpus on every start. The
"8501" not in app_url assertion is untouched: it is a live guard.

No executable line changes.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Streamlit purge — configuration and current-state docs

**Files:**
- Delete: `.streamlit/config.toml` (and the directory)
- Modify: `openspec/config.yaml`
- Modify: `.env.example:68`, `README.md:739` and `:825`, `docs/code-tour.md` (31 occurrences)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Delete the retired UI's config**

```bash
git rm -r .streamlit
```

`git rm` rather than a plain delete: the file is tracked, and the palette reasoning stays recoverable in history. Nothing reads it — `import streamlit` fails, and it is absent from `pyproject.toml` and `uv.lock`.

- [ ] **Step 2: Rewrite `openspec/config.yaml`'s stack description**

The highest-value edit in the lane: this file is loaded as context into every OpenSpec change, and currently briefs each one that the *current* stack is Streamlit + SQLite + Chroma with FastAPI/React as the *target*. Replace the two `## Current stack (being migrated)` and `## Target stack` sections with one:

```yaml
  ## Stack
  Python 3.12, uv. LangGraph state machine for diagnosis (14 nodes, a mandatory
  interrupt() for clarifying questions) plus a LangChain ReAct agent for chat. FastAPI
  backend at the repository root with a React + Vite + TypeScript + Tailwind/shadcn SPA
  in web/. One Postgres holds domain tables, the corpus in pgvector, and both LangGraph
  checkpointers. Own email/password auth with argon2id and rotating JWTs, open
  self-registration, per-user quotas and a global spend cap. Diagnoses run in the
  background with progress streamed over SSE across the interrupt. Every model call
  routes through OpenRouter (gate / vision / reasoning / embedding tiers). Ragas
  evaluation harness over a 28-case golden set; LangSmith tracing optional.
```

Three further corrections in the same file:
- `Layering is ui/api -> services -> agent + data` → `Layering is api -> services -> agent + data`.
- `Markers: integration, ui, llm` → `Markers: integration, llm` — `pyproject.toml` defines only those two.
- The layout claim: it describes `backend/` and `frontend/`, which was never built. The rewrite above says "at the repository root" and `web/`, which is what exists.

**Leave the Chroma wording alone if any remains outside the block you replaced** — Task B rewrites it again, and one owner per sentence avoids a conflict. The block above already says pgvector because that is what the config *should* say once B lands; if A ships alone, this is the one sentence that runs ahead of the code. Note that in the commit body.

- [ ] **Step 3: `.env.example`**

Line 68's aside — "it pointed at Streamlit's retired port for a while, which is exactly that" → "it pointed at a retired UI's port for a while, which is exactly that."

- [ ] **Step 4: `README.md`**

Two sites. Line 739 "The `ui` tier went with Streamlit" and line 825 "used to render them went with Streamlit". Read each in context; both are current-state prose explaining why something is absent. Reword to "went with the retired UI" — the fact is the removal, not which framework it was.

- [ ] **Step 5: `docs/code-tour.md`** — 31 occurrences

The largest single file in the lane and a current-state tour, so it must not describe Streamlit as present. Work through it top to bottom:

```bash
grep -n -i 'streamlit\|8501\|ui/components\|ui/pages' docs/code-tour.md
```

For each: if it describes the architecture *now*, rewrite it to the API/React reality. If it narrates history ("this used to..."), reword to "a retired UI" and keep the tense. Do not delete whole passages that explain why something is shaped as it is — that reasoning is the file's value.

- [ ] **Step 6: Verify the purge**

```bash
git ls-files | while read -r f; do grep -ohE 'streamlit|Streamlit|8501|ui/components|ui/pages' "$f" 2>/dev/null; done | wc -l
```

Expected: **264** — 258 in Tier 3 historical records plus 6 `8501`-in-hash coincidences in `uv.lock`. Then confirm the remainder is only Tier 3 and `uv.lock`:

```bash
git ls-files | while read -r f; do c=$(grep -ocE 'streamlit|Streamlit|8501|ui/components' "$f" 2>/dev/null); [ "$c" != "0" ] && echo "$c $f"; done
```

Expected files: `uv.lock`, `docs/plans/*`, `docs/superpowers/specs/*`, `docs/known-limitations.md`, `openspec/changes/archive/*`, `project_brief_*.md`. **Nothing else.**

- [ ] **Step 7: Run the suites and commit**

```bash
uv run pytest && cd web && npx tsc -b && npm test
git add -A
git commit -m "$(cat <<'EOF'
docs: delete the retired UI's config, and brief OpenSpec on the real stack

openspec/config.yaml is loaded into every OpenSpec change and still described
the current stack as Streamlit + SQLite + Chroma with FastAPI and React as the
target -- so every change started from a briefing that was wrong about the
present. It also named a backend/ + frontend/ layout that was never built and
a ui pytest marker that pyproject no longer defines.

Its corpus sentence now reads pgvector, which runs one change ahead of the
code until the retrieval move lands.

.streamlit/config.toml is removed with git rm rather than deleted: nothing
reads it -- streamlit is not installed and not in the lockfile -- and its
palette reasoning stays recoverable in history. None of its six hex values
appear in web/src, and it asserted the app has no dark mode, which the React
client has had since the frontend pass.

258 mentions remain in dated plans, archived changes and two course briefs, by
decision: editing a dated record produces a document that never existed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Read the product name from settings in `api/errors.py`

**The table refactor this task originally specified is cancelled.** Measured against the
real file rather than the plan's estimate: of 21 handlers only **8** are pure
`status + type + title + static detail`. Thirteen genuinely need code — `UploadRejected`,
`MissingAnswerError`, `RunConflictError`, `QuotaExceededError`, `DailyCapReachedError`,
`ExportTooLargeError`, `ConfirmationError`, `PasswordChangeError` and `ValueError` all read
the exception; `QueueFullError` and `RateLimitedError` set a `Retry-After` header; and the
`Exception` catch-all logs with a documented `exc_info=exc` that must not be disturbed.

Collapsing the remaining 8 would occupy ~96 lines as a dataclass, a registration loop and
8 rows, against the ~89 they occupy today — a **net gain of about 7 lines** — and would
leave the file with *two* patterns instead of one, so a new failure would have two places
it might belong. That is the opposite of the uniformity the refactor was for. Dropped.

What remains is the part the owner asked for directly.

**Files:**
- Modify: `api/errors.py` — `register`'s signature and two `detail` strings
- Modify: `api/main.py:43`

**Interfaces:**
- Consumes: nothing.
- Produces: **`register(app: FastAPI, settings: Settings) -> None`**. `api/main.py:43` is its
  only caller — `tests/api/test_error_shape.py` and `test_refusal_types.py` import only the
  `TYPE_*` constants (verified), so no test breaks.

- [ ] **Step 1: Record the baseline**

```bash
uv run pytest tests/api/ -v 2>&1 | tail -5
```

Note the pass count. It must be identical at the end.

- [ ] **Step 2: Take settings at registration**

In `api/errors.py`, add `from core.config import Settings` to the imports and change:

```python
def register(app: FastAPI, settings: Settings) -> None:
    """Install the handlers that turn exceptions into problem details.

    Takes settings rather than calling ``get_settings()`` inside a handler, and the
    difference is not stylistic: ``get_settings`` is ``lru_cache``d, so a handler calling it
    would read the process-wide singleton and quietly ignore the settings a test passed to
    ``create_app``. Closing over what the factory was given is the only version that stays
    truthful under an injected configuration.
    """
```

Every handler is already nested inside `register`, so all of them can see `settings` through
the closure with no further plumbing.

- [ ] **Step 3: Use `app_title` in the two messages**

Both occurrences are in handlers that stay explicit, so neither needs a placeholder
mechanism. `QueueFullError`:

```python
            detail=f"{settings.app_title} is working through a queue. Try again in a minute.",
```

`DailyCapReachedError`:

```python
            detail=f"{settings.app_title} has reached its spending limit for today. Try again tomorrow.",
```

Leave `api/main.py`'s `FastAPI(title="Plantopia", ...)` alone — that is the OpenAPI document's
title, not user-facing copy, and `core/config.py`'s own default stays a literal because it is
the definition.

- [ ] **Step 4: Update the caller**

`api/main.py:43`:

```python
    errors.register(app, settings)
```

`create_app` already has `settings` in scope on the line above.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/api/ -v && uv run pytest
```

Expected: the **same** pass count as Step 1. A missed caller shows up as a `TypeError` at app
construction, which fails loudly rather than subtly.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check api/ && uv run ruff format api/
git add api/errors.py api/main.py
git commit -m "$(cat <<'EOF'
refactor: read the product name from settings in the error copy

The busy and daily-cap messages hardcoded "Plantopia" while settings.app_title
already existed. register() now takes settings and the nested handlers close
over them.

Passed in rather than fetched: get_settings is lru_cached, so a handler calling
it would read the process singleton and ignore the settings a test passes to
create_app. api/main.py is its only caller -- the two error tests import only
the TYPE_ constants.

The table refactor planned for this file is dropped. Only 8 of 21 handlers are
simple enough to become rows: thirteen read the exception, set a Retry-After
header, or log with a documented exc_info. Collapsing the remaining 8 measured
at about 7 lines *added*, and would leave two patterns in one file so a new
failure had two places it might belong.

Closes M13.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Record the change

**Files:**
- Modify: `docs/known-limitations.md`

- [ ] **Step 1: Strike the resolved rows**

Following the file's convention — struck through and dated, never deleted. Strike `U3`, `U8`, `M13`, `M50`, `M52`. `M13` closes fully: the intake and chat-events occurrences go in Task 3 and the two error-copy ones in Task 7, so no hardcoded product name survives outside `core/config.py`'s own default. For each, add the date and what the fix cost, not just that it closed.

- [ ] **Step 2: Record M54 as not achievable**

`M54` asked that the placeholder replacing cleared tool output name the tool. Do **not** strike it. Amend its "Fix if it matters" column:

```
Not achievable as written. `[cleared]` is the default of LangChain's `ClearToolUsesEdit`,
whose signature is `placeholder: str = '[cleared]'` — a static string with no per-call
hook, so the placeholder cannot name the tool it replaced. The only available change is a
longer static string, which tells a model nothing more. Verified 2026-09-04.
```

- [ ] **Step 3: Add the delete-plant bug as a resolved row**

It was never carried, so it arrives struck: found and fixed on 2026-09-04, with the prefix-matching cause recorded — a future reader adding a query key needs to know that `keys.plants` is a prefix of `keys.plant(id)`.

- [ ] **Step 4: Verify the numbers**

Every figure in the rows you wrote must be checkable from the repository. Confirm the 1568 cap, the 8 MB and 4-image limits, and Node 22 against the files before committing.

- [ ] **Step 5: Commit**

```bash
git add docs/known-limitations.md
git commit -m "$(cat <<'EOF'
docs: strike five carried items, and record one that cannot be done

U3, U8, M13, M50 and M52 close. Each row keeps what the fix cost rather than
only that it shipped.

M54 is not struck. It asked that the placeholder replacing cleared tool output
name the tool, and ClearToolUsesEdit takes a static string with no per-call
hook -- so the item cannot be done as written, which is worth more to the next
reader than a third deferral.

The delete-plant error screen arrives already struck: it was found and fixed in
the same change. Its cause is recorded because it generalises -- keys.plants is
a prefix of keys.plant(id), so anyone adding a query key inherits the trap.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage.** Lane 1 (Streamlit) → Tasks 5 and 6. Lane 2 (dead code) → Task 4. Lane 3's five items → Task 2 (U3), Task 3 (U8, M13, M52), Task 1 (delete-plant); M54's non-fix → Task 8. Lane 4 (`api/errors.py`) → Task 7, reduced to the settings threading after measurement falsified the refactor's premise (see that task's preamble). Testing section → each task's own run steps. Tier 3 protection → Global Constraints and Task 6 Step 6. No spec section is unimplemented.

**Ordering.** Task 1 is first because it is the only live user-facing bug. Tasks 5 and 6 are late because they are the widest diffs and the least risky, so a conflict with them is cheap. Task 8 is last because it records the rest.

**Known soft spots, flagged rather than hidden.** Task 3 Step 4 may find that `api/errors.py`'s handlers cannot reach `settings` — the instruction is to leave those two occurrences and say so, not to thread a dependency. Task 6 Step 2 writes "pgvector" into `openspec/config.yaml` one change ahead of the code. Task 2's `_jpeg_with_capture_date` helper is deliberately delegated to whatever `tests/unit/core/test_metadata.py` already has, because a third hand-rolled EXIF builder is worse than a shared one.
