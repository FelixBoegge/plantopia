# Run activity as a sidebar, and afterwards

**Status:** approved 2026-09-01. Not yet implemented.

## What this changes

Three things, from `frontend_improvements.md`:

1. "What Plantopia is doing" moves from an inline list on the diagnosis screen into a
   left-hand column beside the run.
2. Each step says what it actually called — the configured model, or the external service —
   and how long it took.
3. The log survives the run: a finished diagnosis can show what was consulted to produce it.

## What it deliberately does not change

**No per-step tokens or cost.** An earlier draft attributed spend to each step by diffing
the run-wide `UsageCollector` either side of every node. It was the riskiest part of the
design for the least return: the attribution is only correct while the graph runs its nodes
strictly in sequence, and it fails *silently* — the numbers stay plausible and become wrong.
Run-wide cost already exists on `diagnoses.cost_usd` and reaches the client on
`DiagnosisOut`, which is the granularity that was actually wanted.

**No new table and no migration.** Every step is already persisted: `_publish_step` in
`runs/worker.py` writes to `run_events` *before* publishing, precisely so a reconnect cannot
replay a shorter history than the one on screen. `runs.diagnosis_id` links a run to what it
produced. The history asked for is already in the database; only a read path is missing.

**No change to any screen other than the diagnosis wizard.** `SignedIn.tsx` keeps its single
centred column.

## 1. The step payload

`_publish_step` writes `{step, description}`. It gains two optional fields:

```json
{
  "step": "identifying",
  "description": "Identifying the species",
  "calls": "google/gemini-2.5-flash via OpenRouter",
  "duration_ms": 4120
}
```

Both are optional and both must stay optional. Events written before this change are
replayed to clients on reconnect and will never carry them, so a client that requires them
breaks on any run that started earlier.

## 2. Where the two facts come from

### `calls`

A static map beside `STEPS` in `runs/steps.py`, from node name to either a **model role** or
an **external service**. A role is resolved against `Settings` when the step is published, so
the string names the model actually configured rather than one hardcoded at the time of
writing. A service is a literal: Pl@ntNet, Open-Meteo, OpenStreetMap, the disorder
reference.

Rejected alternative: reading the model id off the LangChain callback. It reports the name
inconsistently across providers, so some steps would say nothing and the gaps would look
like steps that called nothing at all.

Steps that call neither — `persist`, `build_roadmap` — omit the field rather than inventing
a value.

### `duration_ms`

Measured in the worker's `graph.stream` loop: the interval between the previous step's
publish and this one. This is node wall-time and includes graph overhead, so it is *not* the
model's own latency. The UI says "took 4.1s" and never implies otherwise.

## 3. The sidebar

Two columns on the wizard, and nowhere else. `Reasoning` moves into the left column; the
questions, the identification chooser and the result stay on the right.

Below the `sm` breakpoint it stacks to one column with activity **first** — on a phone,
during a ninety-second run, the progress is the screen.

`aria-live="polite"` on the step list is unchanged. It is the only way somebody who cannot
see the screen knows anything is happening, and moving an element does not change that.

## 4. Reading it back

A finished diagnosis finds its run by `runs.diagnosis_id`, and that run's `STEP` events are
the log.

Exposed as **its own endpoint**, not folded into `DiagnosisDetailOut`. That schema's own
docstring gives the rule: the diagnosis and its roadmap travel together because both are
read on every screen that shows either. The activity log is not — it is a panel somebody
opens. Adding it there would make every diagnosis fetch carry a payload most callers ignore.

Ownership is enforced the way every other run-scoped read is: through the repository, which
already refuses another owner's records, so an unknown diagnosis and somebody else's answer
the same way.

## Components

| Layer | Change |
|---|---|
| `runs/steps.py` | node → model role or service, beside the existing `STEPS` map |
| `runs/worker.py` | measure the interval; resolve the role against `Settings`; widen the payload |
| `api` | one endpoint returning a diagnosis's step log |
| `services` | find the run for a diagnosis, read its `STEP` events |
| `web` `Wizard.tsx` | two-column layout, stacking to one |
| `web` `Reasoning.tsx` | render `calls` and `duration_ms` when present |
| `web` diagnosis page | the same list, for a finished run |

## Testing

- A step published with a model role names the configured model, and changing the setting
  changes the string. Pins that the model is not hardcoded.
- A step that calls nothing omits `calls` entirely rather than sending an empty string.
- A replayed event without the new fields still renders. This is the compatibility promise,
  and it is the one that breaks quietly.
- The activity endpoint refuses another owner's diagnosis exactly as the rest of the API
  does.
- The step list keeps `aria-live="polite"` after the layout change.

## Optional, not included

`cost_usd` is already on `DiagnosisOut` and is not displayed anywhere. Showing the run's
total on the finished diagnosis is a one-line addition, and is left out of this change
because it was not asked for.
