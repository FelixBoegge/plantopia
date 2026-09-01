# Run Activity Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move "What Plantopia is doing" into a left-hand column beside the running diagnosis, have each step name the model or service it called and how long it took, and let a finished diagnosis show the same log.

**Architecture:** Two optional fields (`calls`, `duration_ms`) are added to the step event the worker already persists to `run_events`. `calls` resolves a static node→role/service map against `Settings` at publish time, so it names the configured model rather than a hardcoded one. Nothing new is stored: a finished diagnosis finds its run through `runs.diagnosis_id` and reads that run's `STEP` events back through a new endpoint.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest · React 19, TypeScript, Tailwind 4, vitest, MSW

**Spec:** `docs/superpowers/specs/2026-09-01-run-activity-sidebar-design.md`

## Global Constraints

- `calls` and `duration_ms` are **optional in perpetuity**. Events written before this change replay to clients on reconnect and will never carry them. No client may require either.
- A step that calls neither a model nor a service **omits `calls`** rather than sending `""` or `null`.
- `duration_ms` is node wall-time including graph overhead. UI copy says "took 4.1s" and never implies model latency.
- Ownership is enforced through the repository, as everywhere else: another owner's diagnosis is a 404, never a 403.
- `aria-live="polite"` on the step list must survive the layout change.
- Vocabulary: a run is a **diagnosis**, never a "check". Irregular plural — `diagnos${n === 1 ? "is" : "es"}`.
- Backend commands: `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`. Frontend, from `web/`: `npx vitest run`, `npx tsc -b`.

---

### Task 1: What each step calls

**Files:**
- Modify: `runs/steps.py`
- Test: `tests/unit/runs/test_steps.py`

**Interfaces:**
- Consumes: nothing
- Produces: `steps.calls_for(node: str, settings: Settings) -> str | None`, and `steps.CALLS: dict[str, tuple[str, ...]]`

- [ ] **Step 1: Write the failing test**

Create or extend `tests/unit/runs/test_steps.py`:

```python
from core.config import Settings
from runs import steps
from tests.secrets import TEST_JWT_SECRET


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, openrouter_api_key="sk-test", jwt_secret=TEST_JWT_SECRET, **overrides
    )


def test_a_model_step_names_the_configured_model():
    """Not a hardcoded string: swapping the model in settings has to change what the screen
    says, or the screen is lying the first time somebody swaps one."""
    resolved = steps.calls_for("assess_symptoms", _settings(vision_model="acme/see-1"))

    assert resolved == "acme/see-1 via OpenRouter"


def test_a_step_that_uses_two_things_names_both_in_order():
    resolved = steps.calls_for("identify_plant", _settings(vision_model="acme/see-1"))

    assert resolved == "acme/see-1 via OpenRouter, then Pl@ntNet"


def test_a_service_step_names_the_service():
    assert steps.calls_for("enrich", _settings()) == "the disorder reference, then Open-Meteo"


def test_a_step_that_calls_nothing_says_nothing():
    """`persist` writes rows. Inventing a value for it would put a sentence on screen that
    describes no work."""
    assert steps.calls_for("persist", _settings()) is None


def test_an_unmapped_node_says_nothing_rather_than_guessing():
    assert steps.calls_for("a_node_nobody_has_written_yet", _settings()) is None


def test_every_mapped_node_is_a_node_that_has_a_step():
    """The two maps are keyed by the same node names and drift apart silently otherwise."""
    assert set(steps.CALLS) <= set(steps.STEPS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/runs/test_steps.py -q --no-cov`
Expected: FAIL with `AttributeError: module 'runs.steps' has no attribute 'calls_for'`

- [ ] **Step 3: Write minimal implementation**

Append to `runs/steps.py`:

```python
# Settings attributes that name a model. Anything in CALLS that is not one of these is the
# name of an outside service, written as somebody should read it.
MODEL_ROLES = frozenset({"gate_model", "vision_model", "reasoning_model"})

# What each node reaches for, in the order it reaches for it.
#
# Deliberately beside STEPS and keyed the same way: a node whose work changes needs both
# entries updated, and having them adjacent is the only thing that makes that likely. Nodes
# that call neither a model nor a service are absent rather than present-and-empty.
CALLS: dict[str, tuple[str, ...]] = {
    "guard_input": ("gate_model",),
    "quality_check": ("gate_model",),
    "identify_plant": ("vision_model", "Pl@ntNet"),
    "assess_symptoms": ("vision_model",),
    "select_questions": ("reasoning_model", "OpenStreetMap"),
    "hypothesise": ("reasoning_model",),
    "enrich": ("the disorder reference", "Open-Meteo"),
    "diagnose": ("reasoning_model",),
    "check_contagion": ("reasoning_model",),
    "build_roadmap": ("reasoning_model",),
    "revise_roadmap": ("reasoning_model",),
}


def calls_for(node: str, settings) -> str | None:
    """What this node called, in words, or ``None`` where it called nothing outside.

    A model is named from ``settings`` rather than written out here, so the sentence follows
    the configuration instead of describing whichever model was current when this was typed.
    """
    parts = CALLS.get(node)
    if not parts:
        return None
    return ", then ".join(
        f"{getattr(settings, part)} via OpenRouter" if part in MODEL_ROLES else part
        for part in parts
    )
```

Add `calls_for`, `CALLS` and `MODEL_ROLES` to `__all__` if the module defines one.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/runs/test_steps.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add runs/steps.py tests/unit/runs/test_steps.py
git commit -m "feat: say which model or service each diagnosis step calls"
```

---

### Task 2: Publish what it called and how long it took

**Files:**
- Modify: `runs/worker.py` (`_drive`, `_publish_step`)
- Test: `tests/unit/runs/test_worker.py`

**Interfaces:**
- Consumes: `steps.calls_for(node, settings) -> str | None` from Task 1
- Produces: step event payloads carrying optional `calls: str` and `duration_ms: int`

- [ ] **Step 1: Write the failing test**

Add to the worker's existing test module (match its fixtures for building a run; if it uses a fake bus, assert against the events it collected):

```python
def test_a_step_says_what_it_called(worker_run):
    """The screen names the model. It can only do that if the event does."""
    published = worker_run(nodes=["assess_symptoms"])

    [step] = [event for event in published if event.kind == steps.STEP]
    assert step.payload["calls"].endswith("via OpenRouter")


def test_a_step_that_calls_nothing_carries_no_calls_key(worker_run):
    """Absent, not empty. A client renders the key when it is there, and an empty string
    would render as a blank line where a sentence goes."""
    published = worker_run(nodes=["persist"])

    [step] = [event for event in published if event.kind == steps.STEP]
    assert "calls" not in step.payload


def test_a_step_carries_how_long_it_took(worker_run):
    published = worker_run(nodes=["assess_symptoms"])

    [step] = [event for event in published if event.kind == steps.STEP]
    assert isinstance(step.payload["duration_ms"], int)
    assert step.payload["duration_ms"] >= 0
```

If no `worker_run` fixture exists, build one in the test module that drives `_drive` with a `build_graph` stub streaming `{node: {}}` for each name in `nodes`, and returns the events the fake bus received. The worker's existing tests already stub `build_graph`; follow that pattern rather than inventing a second one.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/runs/test_worker.py -q --no-cov`
Expected: FAIL with `KeyError: 'calls'` and `KeyError: 'duration_ms'`

- [ ] **Step 3: Write minimal implementation**

In `runs/worker.py`, import `monotonic`:

```python
from time import monotonic
```

Change `_publish_step` to take the settings and the elapsed time:

```python
def _publish_step(runs, session, bus, run_id, node: str, *, settings, duration_ms: int) -> None:
    """Record one node's completion, then tell whoever is watching.

    Persisted first, always. Publishing first would mean a client receiving an event the
    database does not have, and a reconnect replaying a shorter history than the one
    already on screen.

    `calls` is omitted where the node called nothing outside the process, rather than sent
    empty: a client renders the key when it is present, and an empty one is a blank line
    where a sentence belongs.
    """
    step = steps.step_for(node)
    payload = {"step": step.id, "description": step.description, "duration_ms": duration_ms}
    calls = steps.calls_for(node, settings)
    if calls is not None:
        payload["calls"] = calls
    with transaction(session):
        sequence = runs.append_event(run_id, kind=steps.STEP, payload=payload, now=_now())
    bus.publish(Event(run_id=run_id, sequence=sequence, kind=steps.STEP, payload=payload))
```

In `_drive`, keep a mark and advance it at each publish:

```python
    interrupted = False
    # Wall-time between publishes. It includes the graph's own overhead between nodes, which
    # is why the client says "took 4.1s" rather than presenting it as the model's latency.
    mark = monotonic()
    for update in graph.stream(payload, config, stream_mode="updates"):
        if runs.cancel_requested(run_id):
            raise RunCancelledError

        for node, value in update.items():
            if node == "__interrupt__":
                interrupted = True
                _pause(runs, session, bus, run_id, value)
                break
            now = monotonic()
            _publish_step(
                runs,
                session,
                bus,
                run_id,
                node,
                settings=settings,
                duration_ms=int((now - mark) * 1000),
            )
            mark = now

        if interrupted:
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/runs -q --no-cov`
Expected: PASS. Then `uv run pytest -q` — the graph and API suites also assert on step payloads, and any that compare a payload dict exactly need the two new keys added.

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add runs/worker.py tests/
git commit -m "feat: carry what a step called and how long it took"
```

---

### Task 3: Read a finished diagnosis's steps back

**Files:**
- Modify: `data/repositories/runs.py`
- Modify: `services/run_service.py`
- Test: `tests/unit/data/test_run_repository.py` (or the module holding `RunRepository` tests)

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `RunRepository.steps_for_diagnosis(user_id: UUID, diagnosis_id: UUID) -> list[EventRecord]` and `RunService.activity(diagnosis_id: UUID) -> list[EventRecord]`

- [ ] **Step 1: Write the failing test**

```python
def test_the_steps_of_the_run_that_produced_a_diagnosis_are_readable(repo, run_with_diagnosis):
    run_id, diagnosis_id, user_id = run_with_diagnosis
    repo.append_event(run_id, kind=steps.STEP, payload={"step": "identifying"}, now=_AT)
    repo.append_event(run_id, kind=steps.COMPLETED, payload={"diagnosis_id": str(diagnosis_id)}, now=_AT)

    found = repo.steps_for_diagnosis(user_id, diagnosis_id)

    assert [event.payload["step"] for event in found] == ["identifying"]


def test_another_owners_diagnosis_reads_as_empty(repo, run_with_diagnosis, other_user):
    """Scoped through the run, like every other read here. A stranger holding an identifier
    learns nothing from it."""
    run_id, diagnosis_id, _ = run_with_diagnosis
    repo.append_event(run_id, kind=steps.STEP, payload={"step": "identifying"}, now=_AT)

    assert repo.steps_for_diagnosis(other_user, diagnosis_id) == []


def test_a_diagnosis_with_no_run_reads_as_empty(repo, user_id):
    assert repo.steps_for_diagnosis(user_id, uuid4()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/data/test_run_repository.py -q --no-cov`
Expected: FAIL with `AttributeError: 'RunRepository' object has no attribute 'steps_for_diagnosis'`

- [ ] **Step 3: Write minimal implementation**

In `data/repositories/runs.py`, beside `events`:

```python
    def steps_for_diagnosis(self, user_id: UUID, diagnosis_id: UUID) -> list[EventRecord]:
        """The step events of the run that produced this diagnosis, in order.

        Owner-scoped through the run for the same reason `events` is: the identifier is the
        only thing a stranger would otherwise need.

        Only `STEP` events. The rest of a run's history — the questions it paused on, how it
        ended — belongs to the run, not to the result, and the screen reading this is showing
        what was consulted.
        """
        rows = self._session.scalars(
            select(RunEvent)
            .join(Run, Run.id == RunEvent.run_id)
            .where(
                Run.user_id == user_id,
                Run.diagnosis_id == diagnosis_id,
                RunEvent.kind == steps.STEP,
            )
            .order_by(RunEvent.sequence)
        ).all()
        return [
            EventRecord(
                sequence=row.sequence,
                kind=row.kind,
                payload=json.loads(row.payload_json),
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
```

Import `steps` in that module if it is not already imported (`from runs import steps`); if that creates a cycle, compare against the literal `"step"` and leave a comment saying why.

In `services/run_service.py`, beside `events`:

```python
    def activity(self, diagnosis_id: UUID) -> list[EventRecord]:
        """What the run that produced this diagnosis did, for a screen showing the result."""
        return self._runs.steps_for_diagnosis(self._user_id, diagnosis_id)
```

Match the surrounding code for how the owner is reached — if `events` takes `user_id` as an argument rather than holding it, do the same here.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/data tests/unit/services -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add data/repositories/runs.py services/run_service.py tests/
git commit -m "feat: read back the steps that produced a diagnosis"
```

---

### Task 4: The activity endpoint

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routers/diagnoses.py`
- Test: `tests/api/test_diagnoses.py` (or the module covering `/diagnoses`)

**Interfaces:**
- Consumes: `RunService.activity(diagnosis_id) -> list[EventRecord]` from Task 3
- Produces: `GET /api/v1/diagnoses/{diagnosis_id}/activity -> list[ActivityStepOut]`

- [ ] **Step 1: Write the failing test**

```python
def test_the_activity_of_a_diagnosis_is_its_steps(client, signed_in, diagnosis_with_steps):
    response = client.get(f"/api/v1/diagnoses/{diagnosis_with_steps}/activity")

    assert response.status_code == 200
    [first, *_] = response.json()
    assert first["step"] == "identifying"
    assert first["calls"] == "google/gemini-2.5-flash via OpenRouter, then Pl@ntNet"
    assert first["duration_ms"] == 4120


def test_a_step_recorded_before_this_existed_still_reads(client, signed_in, old_diagnosis):
    """Events already in the database carry neither key. They are replayed on reconnect and
    read here, so both have to be optional for good."""
    response = client.get(f"/api/v1/diagnoses/{old_diagnosis}/activity")

    assert response.status_code == 200
    assert response.json()[0]["calls"] is None
    assert response.json()[0]["duration_ms"] is None


def test_another_owners_diagnosis_is_not_readable(client, signed_in, someone_elses_diagnosis):
    response = client.get(f"/api/v1/diagnoses/{someone_elses_diagnosis}/activity")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_diagnoses.py -q --no-cov`
Expected: FAIL with 404 on the first two (the route does not exist)

- [ ] **Step 3: Write minimal implementation**

In `api/schemas.py`:

```python
class ActivityStepOut(BaseModel):
    """One thing a diagnosis run did.

    `calls` and `duration_ms` are optional and stay optional: events recorded before they
    existed are read through this same shape.
    """

    sequence: int
    step: str
    description: str
    calls: str | None = None
    duration_ms: int | None = None
    occurred_at: datetime
```

In `api/routers/diagnoses.py`:

```python
@router.get("/{diagnosis_id}/activity", response_model=list[ActivityStepOut])
def get_activity(
    diagnosis_id: UUID, runs: RunServiceDep, service: PlantServiceDep, owner: OwnerDep
) -> list[ActivityStepOut]:
    """What the run that produced this diagnosis did.

    Its own endpoint rather than a field on the diagnosis: `DiagnosisDetailOut` carries the
    diagnosis and its roadmap together because both are read on every screen showing either,
    and this is not — it is a panel somebody opens.

    A diagnosis nobody owns and a diagnosis that does not exist answer the same way, which is
    the rule everywhere else here.
    """
    if service.get_diagnosis(diagnosis_id) is None:
        raise RecordNotFoundError(f"no diagnosis {diagnosis_id}")

    return [
        ActivityStepOut(
            sequence=event.sequence,
            step=event.payload["step"],
            description=event.payload["description"],
            calls=event.payload.get("calls"),
            duration_ms=event.payload.get("duration_ms"),
            occurred_at=event.occurred_at,
        )
        for event in runs.activity(diagnosis_id)
    ]
```

Add `RunServiceDep` and `ActivityStepOut` to that module's imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api -q --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff format . && uv run ruff check .
git add api/schemas.py api/routers/diagnoses.py tests/api/
git commit -m "feat: serve the activity of a finished diagnosis"
```

---

### Task 5: Show what each step called

**Files:**
- Modify: `web/src/api/hooks/useRunStream.ts` (the `Step` type)
- Modify: `web/src/screens/wizard/Reasoning.tsx`
- Test: `web/src/screens/wizard/reasoning.test.tsx` (create)

**Interfaces:**
- Consumes: step events carrying optional `calls` and `duration_ms` from Task 2
- Produces: `Step` widened with `calls?: string; duration_ms?: number`

- [ ] **Step 1: Write the failing test**

Create `web/src/screens/wizard/reasoning.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";

import { Reasoning } from "@/screens/wizard/Reasoning";
import { render, screen } from "@/test/render";

const STEP = {
  sequence: 1,
  step: "identifying",
  description: "Identifying the species",
};

describe("the activity list", () => {
  it("names what a step called", async () => {
    render(
      <Reasoning
        steps={[{ ...STEP, calls: "acme/see-1 via OpenRouter" }]}
        working={false}
        connected
      />,
    );

    expect(await screen.findByText(/acme\/see-1 via OpenRouter/)).toBeInTheDocument();
  });

  it("says how long a step took, in seconds", async () => {
    render(
      <Reasoning steps={[{ ...STEP, duration_ms: 4120 }]} working={false} connected />,
    );

    expect(await screen.findByText(/took 4\.1s/)).toBeInTheDocument();
  });

  it("renders a step recorded before either was carried", async () => {
    // Replayed history. A client that required them would break on every older run.
    render(<Reasoning steps={[STEP]} working={false} connected />);

    expect(await screen.findByText("Identifying the species")).toBeInTheDocument();
  });

  it("keeps announcing itself", async () => {
    // The only way somebody who cannot see the screen knows a ninety-second run is alive.
    const { container } = render(
      <Reasoning steps={[STEP]} working connected />,
    );

    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `web/`): `npx vitest run src/screens/wizard/reasoning.test.tsx`
Expected: FAIL — the model name and the duration are not rendered

- [ ] **Step 3: Write minimal implementation**

Widen `Step` in `web/src/api/hooks/useRunStream.ts`:

```ts
export interface Step {
  sequence: number;
  step: string;
  description: string;
  /** What it called. Absent on any run that started before this was recorded. */
  calls?: string;
  /** Node wall-time, including the graph's own overhead between nodes. */
  duration_ms?: number;
}
```

Match the existing declaration's shape — if `Step` is a type alias rather than an interface, widen it in place rather than converting it.

In `Reasoning.tsx`, replace the list item body:

```tsx
        {steps.map((step) => (
          <li key={step.sequence} className="grid gap-0.5 text-sm">
            <span>{step.description}</span>
            {step.calls || step.duration_ms !== undefined ? (
              <span className="text-muted-foreground text-xs">
                {step.calls}
                {step.calls && step.duration_ms !== undefined ? " · " : null}
                {/* "took", not "in": this is the wall time of the step, graph overhead
                    included, and it should not read as the model's own latency. */}
                {step.duration_ms !== undefined
                  ? `took ${(step.duration_ms / 1000).toFixed(1)}s`
                  : null}
              </span>
            ) : null}
          </li>
        ))}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `web/`): `npx vitest run && npx tsc -b`
Expected: PASS, no type errors

- [ ] **Step 5: Commit**

```bash
git add web/src/api/hooks/useRunStream.ts web/src/screens/wizard/Reasoning.tsx web/src/screens/wizard/reasoning.test.tsx
git commit -m "feat: show the model and the time behind each step"
```

---

### Task 6: The sidebar

**Files:**
- Modify: `web/src/screens/wizard/Wizard.tsx` (the `Watching` component's returned layout)
- Test: `web/src/screens/wizard/wizard.test.tsx`

**Interfaces:**
- Consumes: `Reasoning` from Task 5, unchanged in signature
- Produces: nothing other tasks depend on

- [ ] **Step 1: Write the failing test**

Add to `wizard.test.tsx`, inside the `describe("watching it work")` block:

```tsx
  it("puts the activity beside the run rather than above it", async () => {
    signedIn();
    streaming(`${STEP_EVENT}`);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByText("Checking the photographs");

    // The column, not the pixels: jsdom lays nothing out, so what is assertable is that the
    // activity and the run body are siblings in a two-column grid rather than stacked.
    const activity = screen.getByRole("region", { name: "What Plantopia is doing" });
    expect(activity.parentElement).toHaveClass("lg:grid-cols-[18rem_1fr]");
  });
```

Use whichever local helper the module already has for a streaming run — `streaming(...)` above stands for it; do not add a second one.

- [ ] **Step 2: Run test to verify it fails**

Run (from `web/`): `npx vitest run src/screens/wizard/wizard.test.tsx`
Expected: FAIL — no such class on the parent

- [ ] **Step 3: Write minimal implementation**

In `Wizard.tsx`, wrap the activity and the run body in a grid. The activity is first in the DOM so that it comes first when the grid collapses — during a run on a phone, the progress is the screen:

```tsx
      <div className="grid gap-8 lg:grid-cols-[18rem_1fr] lg:items-start">
        <Reasoning
          steps={watched.steps}
          working={...}
          connected={...}
        />
        <div className="grid gap-8">
          {/* everything that was below Reasoning before: the questions, the identification
              chooser, the result, the failure notices */}
        </div>
      </div>
```

Keep the props passed to `Reasoning` exactly as they are; this task moves it and nothing else. `Reasoning` already renders a `<section aria-labelledby="progress">`, which is the `region` the test queries.

- [ ] **Step 4: Run test to verify it passes**

Run (from `web/`): `npx vitest run && npx tsc -b`
Expected: PASS. `accessibility.test.tsx` covers `/diagnose` with axe and must stay green.

- [ ] **Step 5: Commit**

```bash
git add web/src/screens/wizard/Wizard.tsx web/src/screens/wizard/wizard.test.tsx
git commit -m "feat: run the diagnosis beside its activity, not below it"
```

---

### Task 7: The activity of a finished diagnosis

**Files:**
- Create: `web/src/api/hooks/activity.ts`
- Modify: `web/src/screens/plants/DiagnosisPage.tsx`
- Test: `web/src/screens/plants/activity.test.tsx` (create)

**Interfaces:**
- Consumes: `GET /api/v1/diagnoses/{id}/activity` from Task 4; `Step` from Task 5
- Produces: `useActivity(diagnosisId: string)` returning TanStack Query state over `Step[]`

- [ ] **Step 1: Write the failing test**

Create `web/src/screens/plants/activity.test.tsx`:

```tsx
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { DiagnosisPage } from "@/screens/plants/DiagnosisPage";
import { render, screen } from "@/test/render";
import { server } from "@/test/server";

const DIAGNOSIS = "01a0-diagnosis";

describe("what produced a finished diagnosis", () => {
  it("lists the steps it took", async () => {
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json([
          {
            sequence: 1,
            step: "identifying",
            description: "Identifying the species",
            calls: "acme/see-1 via OpenRouter",
            duration_ms: 4120,
            occurred_at: "2026-09-01T12:00:00Z",
          },
        ]),
      ),
    );

    render(<DiagnosisPage />, { route: `/diagnoses/${DIAGNOSIS}` });

    expect(await screen.findByText("Identifying the species")).toBeInTheDocument();
    expect(screen.getByText(/acme\/see-1 via OpenRouter/)).toBeInTheDocument();
  });

  it("says nothing at all when there is no record of it", async () => {
    // Diagnoses made before any of this was recorded. An empty heading over an empty list
    // reads as something having gone wrong.
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () => HttpResponse.json([])),
    );

    render(<DiagnosisPage />, { route: `/diagnoses/${DIAGNOSIS}` });

    expect(
      screen.queryByRole("heading", { name: "How this was reached" }),
    ).not.toBeInTheDocument();
  });
});
```

Whatever else `DiagnosisPage` fetches must be stubbed the way the existing `DiagnosisPage` tests stub it; copy that setup rather than writing a new one.

- [ ] **Step 2: Run test to verify it fails**

Run (from `web/`): `npx vitest run src/screens/plants/activity.test.tsx`
Expected: FAIL — nothing fetches or renders the activity

- [ ] **Step 3: Write minimal implementation**

Create `web/src/api/hooks/activity.ts`:

```ts
import { useQuery } from "@tanstack/react-query";

import { request } from "@/api/client";
import type { Step } from "@/api/hooks/useRunStream";

/**
 * What the run that produced a diagnosis did.
 *
 * Its own request rather than part of the diagnosis: it is a panel somebody opens, and
 * folding it into the diagnosis would make every screen showing a result carry it.
 */
export function useActivity(diagnosisId: string) {
  return useQuery({
    queryKey: ["diagnosis-activity", diagnosisId],
    queryFn: () => request<Step[]>(`/diagnoses/${diagnosisId}/activity`),
  });
}
```

Follow the surrounding hooks for query-key shape — if `web/src/app/queries.ts` centralises keys, add this one there instead of inlining it.

In `DiagnosisPage.tsx`, render the panel only when there is something in it:

```tsx
  const { data: activity } = useActivity(diagnosisId);

  ...

  {activity?.length ? (
    <section aria-labelledby="how" className="grid gap-3">
      <h2 id="how" className="text-lg font-medium">
        How this was reached
      </h2>
      <ol className="grid gap-2">
        {activity.map((step) => (
          <li key={step.sequence} className="grid gap-0.5 text-sm">
            <span>{step.description}</span>
            {step.calls || step.duration_ms !== undefined ? (
              <span className="text-muted-foreground text-xs">
                {step.calls}
                {step.calls && step.duration_ms !== undefined ? " · " : null}
                {step.duration_ms !== undefined
                  ? `took ${(step.duration_ms / 1000).toFixed(1)}s`
                  : null}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  ) : null}
```

If this duplicated markup and `Reasoning`'s list item drift apart, extract the item into a shared component at that point — not before, since one is live and announced and the other is static.

- [ ] **Step 4: Run test to verify it passes**

Run (from `web/`): `npx vitest run && npx tsc -b`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/api/hooks/activity.ts web/src/screens/plants/DiagnosisPage.tsx web/src/screens/plants/activity.test.tsx
git commit -m "feat: show how a finished diagnosis was reached"
```

---

### Task 8: Whole-suite verification

**Files:** none

- [ ] **Step 1: Run everything**

```bash
uv run ruff format . && uv run ruff check . && uv run pytest -q
cd web && npx tsc -b && npx vitest run
```

Expected: backend green at 85%+ coverage, frontend green, no type errors.

- [ ] **Step 2: Drive it in the browser**

Start both servers, run a diagnosis, and confirm: the activity sits in a left column, each step names a model or service and a duration, and the finished diagnosis page shows the same list. Stop the servers afterwards.

- [ ] **Step 3: Tick the item and commit**

Change item 10 in `frontend_improvements.md` to `- [x]`.

```bash
git add frontend_improvements.md
git commit -m "docs: tick the run activity sidebar"
```
