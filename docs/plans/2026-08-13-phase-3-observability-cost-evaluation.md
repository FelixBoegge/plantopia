# Plantopia Phase 3 — Observability, Cost, and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the system measurable — add LangSmith tracing and real token/cost capture to every diagnosis (the `M12` fix), and build a Ragas evaluation harness over a text-first golden set that reports diagnostic accuracy and run-to-run stability.

**Architecture:** Two blocks that share one insight — tracing and cost capture are both LangChain callbacks, so they attach at the same seam. A run-scoped `UsageCollector` is passed to `graph.invoke` twice: as a callback (so it observes every model call automatically) and through `configurable` (so the `persist` node can read it and write usage inside the transaction it already owns). The evaluation harness reuses the `Deps` injection seam Phase 1 built for testability: real reasoning model and real retriever, but a scripted vision tier fed from each golden case, so cases are text and no photograph is needed.

**Tech Stack:** Same as Phases 1–2 (Python 3.12, uv, Streamlit, LangGraph, LangChain, OpenRouter, Pydantic v2, SQLite, pytest), plus two **dev-group only** additions: `ragas` for RAG metrics and `pyyaml` for golden-case files. Neither is imported by the shipped app.

**Spec:** [`docs/superpowers/specs/2026-08-13-phase-3-design.md`](../superpowers/specs/2026-08-13-phase-3-design.md) — read it before starting. Background: [`PLAN.md`](../../PLAN.md) §15, §16, §17, §20; [`docs/code-tour.md`](../code-tour.md) §3c.6 for the single-write transaction this must not break; [`docs/known-limitations.md`](../known-limitations.md) for `M12` (which this closes) and the diagnostic-stability finding that motivates the harness.

**The two blocks ship independently.** Tasks 1–7 deliver working observability on their own; tasks 8–15 deliver evaluation. If the phase is cut short after Task 7, what exists is complete and honest.

## Global Constraints

Every task's requirements implicitly include this section — copied from the Phase 2 plan, unchanged.

- **Python `>=3.12`.** Modern syntax: `X | None`, `list[X]`.
- **Package management is `uv` only.** `uv add`, `uv run pytest`, `uv run streamlit run app.py`.
- **Pydantic v2 syntax.** `model_config = ConfigDict(...)`, `@field_validator`, `@model_validator(mode="after")`.
- **No LLM calls and no network calls in unit tests.** Models arrive through `Deps` or an equivalent explicit parameter.
- **Tests assert on structure and control flow, never on generated prose.**
- **Never assert on wall-clock time.** Time arrives through an injected `now: Callable[[], datetime]`.
- **All datetimes are timezone-aware UTC.**
- **Every model call goes through `core/llm.py`'s factories**, which already route through OpenRouter. Never construct a model anywhere else.
- **Model slugs are configuration, never literals in code.**
- **Secrets come from the environment only.**
- **All SQL uses parameterised queries.**
- **Every task ends with a commit.** Conventional prefixes: `feat:`, `test:`, `fix:`, `chore:`, `docs:`.
- **Run `uv run ruff check . && uv run ruff format .` before every commit.**
- **Module docstrings on every module; type hints on every public function.**
- **Repository write methods never commit.** The caller wraps writes in `data.db.transaction(conn)`.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| — | Spike: prove `configurable` carries a live object through checkpointing | 1 |
| `core/cost.py` | New: `UsageSnapshot`, `UsageCollector` callback handler | 2 |
| `core/llm.py` | Ask OpenRouter to report usage | 3 |
| `core/config.py`, `core/tracing.py`, `.env.example` | New: LangSmith settings and opt-in tracing | 4 |
| `data/repositories/diagnoses.py` | `DiagnosisRecord` gains `token_usage` | 5 |
| `agent/nodes/persist.py` | `persist(state, config)` writes usage in the existing transaction | 5 |
| `services/diagnosis_service.py` | Thread-scoped collectors; wire into every `invoke` | 6 |
| `ui/components/cost_badge.py`, `ui/pages/diagnose.py`, `ui/components/timeline.py` | New badge, rendered in two places | 7 |
| `docs/known-limitations.md`, `README.md` | Record `M12` resolved and chat cost as a new gap | 7 |
| `pyproject.toml` | `ragas`/`pyyaml` dev deps; coverage `source`/`omit` | 8 |
| `eval/cases.py`, `eval/golden_set/*.yaml` | New: case schema, loader, and the first three cases | 8 |
| `eval/golden_set/*.yaml` | The remaining cases, to 25–30 | 9 |
| `eval/scripted.py` | New: schema-dispatching model | 10 |
| `eval/harness.py` | New: run one case, return a `CaseRun` | 11 |
| `eval/metrics.py` | New: top-1/top-3 accuracy, stability | 12 |
| `eval/ragas_metrics.py` | New: Ragas wiring, isolated from pure scoring | 13 |
| `eval/report.py`, `eval/run_eval.py` | New: markdown rendering and the CLI | 14 |
| `ui/pages/evaluation.py`, `app.py` | New page rendering committed results | 15 |
| `docs/known-limitations.md`, `README.md`, `eval/REPORT.md` | Phase close-out | 15 |

---

# Block A — Observability and cost

## Task 1: Spike — prove the `configurable` seam carries a live object

The whole cost design rests on one unverified assumption: that LangGraph passes a non-JSON-serialisable object through `config["configurable"]` to a node, and that the SQLite checkpointer does not try to serialise it. Verify before building on it, exactly as `.env.example` documents probing model slugs before depending on them.

**Files:**
- Create: `tests/graph/test_configurable_passthrough.py`

**Interfaces:**
- Produces: a proven (or disproven) assumption for Task 5. No production code.

- [ ] **Step 1: Write the spike test**

```python
"""Spike: can a live object ride through `configurable` into a node?

The Phase 3 cost design passes a `UsageCollector` this way so `persist` can read
it (spec §2.1). A callback object is not JSON-serialisable, and the SQLite
checkpointer writes checkpoint metadata derived from config — so this has to be
proven against the real saver, not assumed.
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel


class _State(BaseModel):
    seen: str = ""


class _NotSerialisable:
    """Stands in for UsageCollector: json.dumps() raises on this."""

    def label(self) -> str:
        return "alive"


def test_configurable_carries_a_live_object_through_checkpointing():
    def node(state: _State, config) -> dict:
        obj = config["configurable"]["probe"]
        return {"seen": obj.label()}

    builder = StateGraph(_State)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    graph = builder.compile(checkpointer=SqliteSaver(conn))

    result = graph.invoke(
        _State(),
        {"configurable": {"thread_id": "spike-1", "probe": _NotSerialisable()}},
    )

    assert result["seen"] == "alive"
    conn.close()
```

- [ ] **Step 2: Run the spike**

Run: `uv run pytest tests/graph/test_configurable_passthrough.py -v`

Expected: **PASS.** If it passes, the design in Task 5 stands as written.

**If it FAILS** (typically a serialisation error from the checkpointer writing metadata), do not fight it. Switch to the fallback the spec records in §2.1: a `contextvars.ContextVar` in `core/cost.py`.

```python
# core/cost.py — fallback shape only, if and only if Step 2 fails
_CURRENT: ContextVar["UsageCollector | None"] = ContextVar("usage_collector", default=None)


@contextmanager
def collecting(collector: "UsageCollector"):
    token = _CURRENT.set(collector)
    try:
        yield collector
    finally:
        _CURRENT.reset(token)


def current_collector() -> "UsageCollector | None":
    return _CURRENT.get()
```

Under the fallback, `persist` calls `current_collector()` instead of reading `config`, and `DiagnosisService` wraps each `invoke` in `with collecting(collector):`. Everything else in this plan is unchanged. **Record which path was taken in the commit message**, because Task 5 and Task 6 depend on it.

- [ ] **Step 3: Commit**

```bash
git add tests/graph/test_configurable_passthrough.py
git commit -m "test: prove configurable carries a live object through checkpointing"
```

---

## Task 2: `UsageCollector`

**Files:**
- Create: `core/cost.py`
- Test: `tests/unit/core/test_cost.py`

**Interfaces:**
- Produces:
  - `UsageSnapshot(prompt_tokens: int, completion_tokens: int, cost_usd: float | None)`, frozen, with `.total_tokens: int` and `.as_token_usage() -> dict[str, int]`
  - `UsageCollector()` — a `BaseCallbackHandler` with `.snapshot() -> UsageSnapshot | None`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for per-run token and cost accounting."""

from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.messages import AIMessage

from core.cost import UsageCollector, UsageSnapshot


def _result(prompt: int, completion: int, cost: float | None = None) -> LLMResult:
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cost is not None:
        usage["cost"] = cost
    return LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="x"))]],
        llm_output={"token_usage": usage, "model_name": "test"},
    )


def test_snapshot_is_none_before_any_call():
    assert UsageCollector().snapshot() is None


def test_accumulates_tokens_across_calls():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))
    collector.on_llm_end(_result(50, 10))

    snapshot = collector.snapshot()
    assert snapshot == UsageSnapshot(prompt_tokens=150, completion_tokens=30, cost_usd=None)
    assert snapshot.total_tokens == 180


def test_accumulates_cost_when_reported():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20, cost=0.0012))
    collector.on_llm_end(_result(50, 10, cost=0.0003))

    assert collector.snapshot().cost_usd == 0.0015


def test_cost_stays_none_when_never_reported():
    """A provider that omits cost must not produce a fabricated $0.00 (spec §5)."""
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))

    assert collector.snapshot().cost_usd is None


def test_partial_cost_reporting_still_sums_what_was_seen():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20, cost=0.001))
    collector.on_llm_end(_result(50, 10))

    assert collector.snapshot().cost_usd == 0.001


def test_falls_back_to_usage_metadata_on_the_message():
    """Some LangChain paths report usage on the message rather than llm_output."""
    message = AIMessage(
        content="x",
        usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    result = LLMResult(generations=[[ChatGeneration(message=message)]], llm_output=None)

    collector = UsageCollector()
    collector.on_llm_end(result)

    assert collector.snapshot() == UsageSnapshot(
        prompt_tokens=7, completion_tokens=3, cost_usd=None
    )


def test_a_call_reporting_no_usage_at_all_is_ignored():
    result = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]])

    collector = UsageCollector()
    collector.on_llm_end(result)

    assert collector.snapshot() is None


def test_as_token_usage_is_json_shaped():
    collector = UsageCollector()
    collector.on_llm_end(_result(100, 20))

    assert collector.snapshot().as_token_usage() == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_cost.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.cost'`

- [ ] **Step 3: Write `core/cost.py`**

```python
"""Per-run token and cost accounting.

Attached to a graph run as a LangChain callback, so it observes every model call
without any node needing to know it exists — including calls from nodes nobody
remembered to instrument. The alternative, accumulating usage in graph state, was
rejected because it would touch every model-calling node and grow the state that
``M15`` already blames for ~100 MB of checkpoint per diagnosis (spec §2.2).

Cost comes from OpenRouter, which reports the credits it actually charged, rather
than from a configured price table that would go stale silently (spec §2.3).
"""

from dataclasses import dataclass
from threading import Lock
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """What one run cost, as of the moment it was taken."""

    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_token_usage(self) -> dict[str, int]:
        """The shape written to ``diagnoses.token_usage_json``."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def _cost_of(usage: dict[str, Any]) -> float | None:
    """OpenRouter's reported cost for one call, or ``None`` if it reported none."""
    raw = usage.get("cost")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class UsageCollector(BaseCallbackHandler):
    """Accumulates token counts and cost across every model call in one run.

    Scoped to a *thread*, not to a single ``invoke``: a diagnosis spans two
    invocations (``start`` pauses at the clarifying-question interrupt, ``answer``
    resumes it), and the vision and gate calls — the expensive ones — all happen in
    the first. A per-invocation collector would silently undercount by roughly half.
    ``DiagnosisService`` owns the lifetime; see spec §2.1.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cost = 0.0
        self._saw_cost = False
        self._calls = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        extracted = self._extract(response)
        if extracted is None:
            return
        prompt_tokens, completion_tokens, cost = extracted
        with self._lock:
            self._calls += 1
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            if cost is not None:
                self._saw_cost = True
                self._cost += cost

    @staticmethod
    def _extract(response: LLMResult) -> tuple[int, int, float | None] | None:
        """Token counts and cost from a result, or ``None`` if it carried neither.

        Two shapes are read because LangChain reports usage in two places depending
        on the path taken: ``llm_output["token_usage"]`` for the OpenAI-compatible
        client, and ``message.usage_metadata`` on the generation itself.
        """
        usage = (response.llm_output or {}).get("token_usage") or {}
        if usage:
            return (
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                _cost_of(usage),
            )

        for generations in response.generations:
            for generation in generations:
                metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if metadata:
                    return (
                        int(metadata.get("input_tokens", 0)),
                        int(metadata.get("output_tokens", 0)),
                        None,
                    )
        return None

    def snapshot(self) -> UsageSnapshot | None:
        """Usage so far, or ``None`` if no model call reported any.

        ``None`` rather than a zeroed snapshot: unit tests run entirely on scripted
        models that report nothing, and writing zeros would make a diagnosis look
        measured when it was not.
        """
        with self._lock:
            if self._calls == 0:
                return None
            return UsageSnapshot(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                # Rounded because floating-point addition of per-call costs
                # accumulates representation noise well below a cent.
                cost_usd=round(self._cost, 8) if self._saw_cost else None,
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_cost.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add core/cost.py tests/unit/core/test_cost.py
git commit -m "feat: add UsageCollector for per-run token and cost accounting"
```

---

## Task 3: Ask OpenRouter to report usage

**Files:**
- Modify: `core/llm.py:33-48`
- Test: `tests/unit/core/test_llm.py`

**Interfaces:**
- Consumes: nothing.
- Produces: every model built by `build_chat_model` now requests usage accounting, so `UsageCollector` has something to read.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/core/test_llm.py` (create it if absent, with the module docstring `"""Unit tests for the chat-model factory."""`):

```python
def test_models_request_usage_accounting():
    """OpenRouter only reports the credits it charged when asked (spec §2.3)."""
    from core.llm import build_chat_model

    model = build_chat_model(model="test/model")

    assert model.extra_body["usage"] == {"include": True}


def test_provider_routing_restriction_is_preserved():
    """The require_parameters guard must survive alongside the usage flag."""
    from core.llm import build_chat_model

    model = build_chat_model(model="test/model")

    assert model.extra_body["provider"] == {"require_parameters": True}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_llm.py -v -k usage`
Expected: FAIL — `KeyError: 'usage'`

- [ ] **Step 3: Add the flag**

In `core/llm.py`, replace the `extra_body` argument of `ChatOpenAI(...)`:

```python
        extra_body={
            # OpenRouter load-balances a model across several upstream providers, and they
            # do not all support the same parameters. Without this, a request can land on
            # a provider that ignores tool calling, and every structured output in the
            # pipeline fails intermittently and unreproducibly. This restricts routing to
            # providers that honour the parameters we send.
            "provider": {"require_parameters": True},
            # Return the credits actually charged for each call. Reading the biller's own
            # number beats maintaining a price table that goes stale every time a price
            # changes or a model is swapped via .env (spec §2.3). UsageCollector reads it.
            "usage": {"include": True},
        },
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/core/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add core/llm.py tests/unit/core/test_llm.py
git commit -m "feat: ask OpenRouter to report per-call usage and cost"
```

---

## Task 4: LangSmith tracing, opt-in and degrading

**Files:**
- Create: `core/tracing.py`
- Modify: `core/config.py:55` (beside `tavily_api_key`), `.env.example`, `ui/bootstrap.py`
- Test: `tests/unit/core/test_tracing.py`

**Interfaces:**
- Consumes: `Settings` from `core/config.py`.
- Produces: `configure_tracing(settings: Settings) -> bool` — returns whether tracing was enabled.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for optional LangSmith tracing."""

from core.config import Settings
from core.tracing import configure_tracing


def _settings(**overrides) -> Settings:
    return Settings(openrouter_api_key="sk-test", **overrides)


def test_tracing_is_disabled_without_a_key(monkeypatch):
    """A fresh clone with no LangSmith account must run unchanged (spec §2.4)."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    assert configure_tracing(_settings()) is False
    assert "LANGSMITH_TRACING" not in __import__("os").environ


def test_tracing_is_enabled_with_a_key(monkeypatch):
    import os

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    enabled = configure_tracing(_settings(langsmith_api_key="ls-test"))

    assert enabled is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-test"
    assert os.environ["LANGSMITH_PROJECT"] == "plantopia"


def test_project_name_is_configurable(monkeypatch):
    import os

    configure_tracing(_settings(langsmith_api_key="ls-test", langsmith_project="phase-3"))

    assert os.environ["LANGSMITH_PROJECT"] == "phase-3"


def test_a_blank_key_counts_as_absent(monkeypatch):
    """An empty PLANTOPIA_LANGSMITH_API_KEY= line in .env must not enable tracing."""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    assert configure_tracing(_settings(langsmith_api_key="   ")) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_tracing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.tracing'`

- [ ] **Step 3: Add the settings**

In `core/config.py`, directly below `tavily_api_key: str | None = None`:

```python
    # LangSmith tracing. Optional in exactly the way tavily_api_key is: absent, the
    # application runs unchanged and tracing is simply off (spec §2.4). Because
    # LangChain's tracer is itself a callback, a key is all the wiring there is —
    # every node, tool call, retrieval and model call is traced automatically.
    langsmith_api_key: str | None = None
    langsmith_project: str = "plantopia"
```

- [ ] **Step 4: Write `core/tracing.py`**

```python
"""Optional LangSmith tracing.

Enabled by configuration alone. LangChain's tracer reads process environment
variables, so this module sets them rather than threading a callback through the
graph — which is the property ``PLAN.md`` §15 chose LangSmith for: every graph
node, tool call, retrieval and model call appears in a trace with no wiring.

Absent a key this is a no-op, following the ``tavily_api_key`` precedent so that a
fresh clone runs without a LangSmith account.
"""

import logging
import os

from core.config import Settings

logger = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> bool:
    """Enable LangSmith tracing when a key is configured.

    Returns:
        ``True`` when tracing was enabled, ``False`` when no usable key was present.
    """
    key = (settings.langsmith_api_key or "").strip()
    if not key:
        logger.info("LangSmith tracing disabled: no API key configured")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info("LangSmith tracing enabled, project %r", settings.langsmith_project)
    return True
```

- [ ] **Step 5: Call it once at bootstrap**

In `ui/bootstrap.py`, inside `get_service()` (or whichever cached factory runs first), add before the `Deps` is built:

```python
    from core.tracing import configure_tracing

    configure_tracing(settings)
```

- [ ] **Step 6: Document the keys**

Append to `.env.example`:

```bash
# Optional — enables LangSmith tracing. Without it the app runs unchanged and
# tracing is simply off. Free Developer tier is ample for this project.
# PLANTOPIA_LANGSMITH_API_KEY=
# PLANTOPIA_LANGSMITH_PROJECT=plantopia
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/core/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add core/tracing.py core/config.py .env.example ui/bootstrap.py tests/unit/core/test_tracing.py
git commit -m "feat: add optional LangSmith tracing"
```

---

## Task 5: Persist usage inside the existing transaction

**Files:**
- Modify: `data/repositories/diagnoses.py:16-41`, `agent/nodes/persist.py`
- Test: `tests/unit/data/test_diagnoses_repository.py`, `tests/unit/nodes/test_persist.py`

**Interfaces:**
- Consumes: `UsageSnapshot`, `UsageCollector` from Task 2; the Task 1 spike verdict.
- Produces: `DiagnosisRecord.token_usage: dict[str, int] | None`; `persist` accepting `(state, config)`.

> **Task 1 dependency.** If the spike passed, implement as written. If it failed, `persist` calls `current_collector()` from `core/cost.py` instead of reading `config`, and the `config` parameter is not added.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/data/test_diagnoses_repository.py`:

```python
def test_token_usage_round_trips(db, now):
    """M12: these columns exist and create() already accepts them — nothing wrote them."""
    from data.repositories.diagnoses import DiagnosisRepository

    repo = DiagnosisRepository(db)
    diagnosis_id = _create_minimal_diagnosis(
        repo,
        db,
        now,
        token_usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        cost_usd=0.0042,
    )

    record = repo.get(diagnosis_id)
    assert record.token_usage == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    assert record.cost_usd == 0.0042


def test_token_usage_is_none_when_not_written(db, now):
    from data.repositories.diagnoses import DiagnosisRepository

    repo = DiagnosisRepository(db)
    diagnosis_id = _create_minimal_diagnosis(repo, db, now)

    record = repo.get(diagnosis_id)
    assert record.token_usage is None
    assert record.cost_usd is None
```

Add the helper at the top of that test module (repeat it rather than importing across test files):

```python
def _create_minimal_diagnosis(repo, db, now, **usage) -> int:
    """A plant, an observation, and one diagnosis. Returns the diagnosis id."""
    from agent.schemas import Candidate, Differential, Severity
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository

    plant_id = PlantRepository(db).create(
        name="Test plant",
        species=None,
        species_confidence=None,
        location_kind="indoor",
        location_text=None,
        photo_ref=None,
        now=now(),
    )
    observation_id = ObservationRepository(db).create(
        plant_id=plant_id, kind="initial", photo_refs=["img-1"], user_notes=None, now=now()
    )
    differential = Differential(
        is_healthy=False,
        reasoning="Test reasoning.",
        candidates=[
            Candidate(
                disorder_id="overwatering",
                name="Overwatering",
                probability=0.8,
                supporting_evidence=["wet soil"],
                contradicting_evidence=[],
                distinguishing_test="Feel the soil three days after watering.",
                severity=Severity.ACT_THIS_WEEK,
                transmissible=False,
            )
        ],
    )
    return repo.create(
        observation_id=observation_id,
        plant_id=plant_id,
        differential=differential,
        contagion=None,
        retrieved=[],
        model="test-model",
        now=now(),
        **usage,
    )
```

Append to `tests/unit/nodes/test_persist.py`:

```python
def test_persist_writes_usage_from_the_collector(make_deps, sample_images, db, now):
    """The collector is read inside persist's transaction, not by a second write."""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from agent.nodes.persist import make_persist
    from core.cost import UsageCollector
    from data.repositories.diagnoses import DiagnosisRepository

    collector = UsageCollector()
    collector.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="x"))]],
            llm_output={"token_usage": {"prompt_tokens": 90, "completion_tokens": 10, "cost": 0.002}},
        )
    )

    deps = make_deps()
    state = _state_ready_to_persist(sample_images)
    config = {"configurable": {"thread_id": "t", "usage_collector": collector}}

    result = make_persist(deps)(state, config)

    record = DiagnosisRepository(db).get(result["diagnosis_id"])
    assert record.token_usage == {
        "prompt_tokens": 90,
        "completion_tokens": 10,
        "total_tokens": 100,
    }
    assert record.cost_usd == 0.002


def test_persist_writes_null_usage_without_a_collector(make_deps, sample_images, db):
    """Every existing caller and every unit test passes no collector. Must not crash."""
    from agent.nodes.persist import make_persist
    from data.repositories.diagnoses import DiagnosisRepository

    result = make_persist(make_deps())(_state_ready_to_persist(sample_images), None)

    record = DiagnosisRepository(db).get(result["diagnosis_id"])
    assert record.token_usage is None
    assert record.cost_usd is None
```

Define `_state_ready_to_persist` in that module, mirroring the `Differential`/`Roadmap` shapes already used by `tests/conftest.py`'s `sample_plant` fixture:

```python
def _state_ready_to_persist(sample_images):
    from agent.schemas import Candidate, Differential, Severity
    from agent.state import DiagnosisState

    return DiagnosisState(
        images=sample_images,
        plant_name="Test plant",
        location_kind="indoor",
        location_text=None,
        user_notes=None,
        differential=Differential(
            is_healthy=False,
            reasoning="Wet soil and lower-leaf yellowing.",
            candidates=[
                Candidate(
                    disorder_id="overwatering",
                    name="Overwatering",
                    probability=0.8,
                    supporting_evidence=["wet soil"],
                    contradicting_evidence=[],
                    distinguishing_test="Feel the soil three days after watering.",
                    severity=Severity.ACT_THIS_WEEK,
                    transmissible=False,
                )
            ],
        ),
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/data/test_diagnoses_repository.py tests/unit/nodes/test_persist.py -v`
Expected: FAIL — `AttributeError: 'DiagnosisRecord' object has no attribute 'token_usage'`, and `TypeError: persist() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Add `token_usage` to the record**

In `data/repositories/diagnoses.py`, add the field to `DiagnosisRecord` immediately above `cost_usd`:

```python
    model: str
    token_usage: dict[str, int] | None
    cost_usd: float | None
    created_at: datetime
```

and parse it in `_to_record`, above the `cost_usd` line:

```python
    token_usage_raw = row["token_usage_json"]
    return DiagnosisRecord(
        ...
        model=row["model"],
        token_usage=json.loads(token_usage_raw) if token_usage_raw else None,
        cost_usd=row["cost_usd"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
```

`create()` already accepts `token_usage` and `cost_usd` and already writes both columns — no change there. That is precisely what `M12` describes: the write path existed and nothing used it.

- [ ] **Step 4: Read the collector in `persist`**

In `agent/nodes/persist.py`, add the import and helper, and change the signature:

```python
from langchain_core.runnables import RunnableConfig

from core.cost import UsageSnapshot


def _usage_from(config: RunnableConfig | None) -> UsageSnapshot | None:
    """The run's usage so far, or ``None`` when no collector was wired.

    ``None`` is the normal case for unit tests and for any caller that has not
    opted in, so this must never raise. By the time this node runs, every model
    call in the run has completed, so the snapshot is final.
    """
    if not config:
        return None
    collector = (config.get("configurable") or {}).get("usage_collector")
    return collector.snapshot() if collector is not None else None
```

Change the node signature and the `create` call:

```python
    def persist(state: DiagnosisState, config: RunnableConfig | None = None) -> dict:
        ...
            usage = _usage_from(config)
            diagnosis_id = deps.diagnoses.create(
                observation_id=observation_id,
                plant_id=plant_id,
                differential=state.differential,
                contagion=state.contagion,
                retrieved=state.retrieved,
                model=deps.settings.reasoning_model,
                now=now,
                token_usage=usage.as_token_usage() if usage else None,
                cost_usd=usage.cost_usd if usage else None,
            )
```

Extend the module docstring's second paragraph:

```python
"""Persist a completed diagnosis.

Every write happens inside one transaction. A half-written diagnosis — a plant with
an observation but no diagnosis, or a diagnosis with no treatment plan — would show
up in the UI as a broken record with no way for the user to fix it.

Token usage and cost are read from the run-scoped collector on ``config`` and written
in that same transaction. A post-run ``UPDATE`` from the service would have been a
smaller change, but it splits one write into two: a crash between them leaves a
diagnosis with NULL cost, which is exactly the state ``M12`` describes (spec §2.2).
"""
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/ tests/graph/ -v`
Expected: PASS. The default `NodeFn = Callable[[DiagnosisState], dict]` alias still type-checks because `config` has a default; existing graph tests that call `persist(state)` are unaffected.

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add data/repositories/diagnoses.py agent/nodes/persist.py tests/unit/
git commit -m "fix: write token usage and cost when persisting a diagnosis (M12)"
```

---

## Task 6: Thread-scoped collectors in `DiagnosisService`

A diagnosis spans **two** graph invocations — `start` runs the gate, vision and question-selection calls then pauses at the interrupt; `answer` resumes and runs the rest. A collector created per `invoke` would miss everything `start` did, which is the vision work and therefore most of the cost. The collector is therefore keyed by `thread_id` and lives until the run reaches a terminal outcome.

**Files:**
- Modify: `services/diagnosis_service.py:68-71, 99, 148, 199, 224-262`
- Test: `tests/unit/services/test_diagnosis_service.py`

**Interfaces:**
- Consumes: `UsageCollector` from Task 2; `persist`'s `configurable` contract from Task 5.
- Produces: usage spanning a whole thread, reaching `persist`.

- [ ] **Step 1: Write the failing tests**

```python
def test_one_collector_spans_start_and_answer(make_deps, pipeline_models, sample_images):
    """The vision calls happen in start(); the persist happens in answer(). One
    collector must see both, or cost undercounts by roughly half."""
    from services.diagnosis_service import DiagnosisService

    service = _service(make_deps, pipeline_models)

    first = service._run_config("thread-a")
    second = service._run_config("thread-a")

    assert first["configurable"]["usage_collector"] is second["configurable"]["usage_collector"]


def test_different_threads_get_different_collectors(make_deps, pipeline_models):
    service = _service(make_deps, pipeline_models)

    a = service._run_config("thread-a")["configurable"]["usage_collector"]
    b = service._run_config("thread-b")["configurable"]["usage_collector"]

    assert a is not b


def test_the_collector_is_also_a_callback(make_deps, pipeline_models):
    """Passed twice on purpose: as a callback to observe calls, and through
    configurable so persist can read it (spec §2.1)."""
    service = _service(make_deps, pipeline_models)

    config = service._run_config("thread-a")

    assert config["callbacks"] == [config["configurable"]["usage_collector"]]


def test_collectors_are_evicted_at_a_terminal_outcome(make_deps, pipeline_models):
    """Otherwise the dict grows for the life of the process."""
    service = _service(make_deps, pipeline_models)
    service._run_config("thread-a")

    service._release("thread-a")

    assert "thread-a" not in service._collectors


def test_releasing_an_unknown_thread_is_harmless(make_deps, pipeline_models):
    service = _service(make_deps, pipeline_models)

    service._release("never-seen")  # must not raise
```

Add the `_service` helper to that module if one is not already present, following the existing construction in `tests/unit/services/test_diagnosis_service.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_diagnosis_service.py -v -k collector`
Expected: FAIL — `AttributeError: 'DiagnosisService' object has no attribute '_run_config'`

- [ ] **Step 3: Add thread-scoped collectors**

In `services/diagnosis_service.py`, import and extend `__init__`:

```python
from core.cost import UsageCollector
```

```python
    def __init__(self, deps: Deps, graph, *, upload_dir: Path) -> None:
        self._deps = deps
        self._graph = graph
        self._upload_dir = upload_dir
        # Keyed by thread_id because a diagnosis spans two invocations: start()
        # pauses at the clarifying-question interrupt and answer() resumes it. The
        # gate and vision calls all happen in the first, so a per-invoke collector
        # would undercount by roughly half. Evicted by _release() at every terminal
        # outcome so this cannot grow for the life of the process.
        self._collectors: dict[str, UsageCollector] = {}
```

Add the two new methods beside `_config`:

```python
    def _run_config(self, thread_id: str) -> dict:
        """Config for an ``invoke``, carrying this thread's usage collector.

        The collector is passed twice deliberately: as a callback, so it observes
        every model call without any node knowing it exists, and through
        ``configurable``, so ``persist`` can read it (spec §2.1).
        """
        collector = self._collectors.setdefault(thread_id, UsageCollector())
        return {
            "configurable": {"thread_id": thread_id, "usage_collector": collector},
            "callbacks": [collector],
        }

    def _release(self, thread_id: str) -> None:
        """Drop a finished thread's collector."""
        self._collectors.pop(thread_id, None)
```

Leave the existing `_config` static method exactly as it is — `get_state` and `update_state` are reads and want no collector.

- [ ] **Step 4: Use it at every `invoke`, and release at every terminal outcome**

In `start`, replace the invoke and guard handling:

```python
        result = self._graph.invoke(state, self._run_config(thread_id))

        stopped = self._stopped_at_the_guards(result)
        if stopped is not None:
            self._release(thread_id)
            return stopped
```

In `answer`:

```python
        result = self._graph.invoke(Command(resume=answers), self._run_config(thread_id))
        final = self._final_result(result, self._collectors[thread_id].snapshot())
        self._release(thread_id)
        return final
```

In `start_recheck`:

```python
        result = self._graph.invoke(state, self._run_config(thread_id))

        stopped = self._stopped_at_the_guards(result)
        if stopped is not None:
            self._release(thread_id)
            return stopped

        final = self._final_result(result, self._collectors[thread_id].snapshot())
        self._release(thread_id)
        return final
```

Note that `answer`'s `config` local (used for `get_state`/`update_state`) still comes from `self._config(thread_id)` and is unchanged.

- [ ] **Step 5: Carry usage on `FinalResult`**

The result view renders immediately after the run and has no repository in scope. Two fields on the result it already holds beat wiring a repository into a page.

Add to `FinalResult`, after `verdict_reasoning`:

```python
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
```

and extend `_final_result`:

```python
    def _final_result(self, result: dict, usage: UsageSnapshot | None = None) -> FinalResult:
        # A ProgressVerdict for a re-check, absent for a first-time diagnosis.
        verdict = result.get("verdict")
        return FinalResult(
            ...
            verdict=verdict.verdict if verdict is not None else None,
            verdict_reasoning=verdict.reasoning if verdict is not None else None,
            token_usage=usage.as_token_usage() if usage else None,
            cost_usd=usage.cost_usd if usage else None,
        )
```

Import `UsageSnapshot` alongside `UsageCollector`. The default of `None` keeps every existing test that calls `_final_result(result)` working unchanged.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`
Expected: PASS, coverage still above 85%.

- [ ] **Step 7: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add services/diagnosis_service.py tests/unit/services/test_diagnosis_service.py
git commit -m "feat: scope usage collectors to a thread so cost spans start and answer"
```

---

## Task 7: The cost badge, and closing `M12`

**Files:**
- Create: `ui/components/cost_badge.py`
- Modify: `ui/pages/diagnose.py`, `ui/components/timeline.py`, `docs/known-limitations.md`, `README.md`
- Test: `tests/ui/test_cost_badge.py`

**Interfaces:**
- Consumes: `DiagnosisRecord.token_usage`/`cost_usd` from Task 5.
- Produces: `render_cost_badge(token_usage: dict[str, int] | None, cost_usd: float | None) -> None`

- [ ] **Step 1: Write the failing tests**

```python
"""UI tests for the cost badge."""

import pytest

pytestmark = pytest.mark.ui


def test_renders_tokens_and_cost():
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(
            {"prompt_tokens": 1240, "completion_tokens": 890, "total_tokens": 2130}, 0.0043
        )

    app = AppTest.from_function(script).run()
    caption = app.caption[0].value
    assert "1,240 in" in caption
    assert "890 out" in caption
    assert "$0.0043" in caption


def test_renders_tokens_only_when_cost_is_unknown():
    """A provider that omits cost must not produce a fabricated $0.00 (spec §5)."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}, None
        )

    app = AppTest.from_function(script).run()
    caption = app.caption[0].value
    assert "100 in" in caption
    assert "$" not in caption


def test_renders_nothing_when_no_usage_was_recorded():
    """Every diagnosis written before Phase 3 has NULL usage."""
    from streamlit.testing.v1 import AppTest

    def script():
        from ui.components.cost_badge import render_cost_badge

        render_cost_badge(None, None)

    app = AppTest.from_function(script).run()
    assert len(app.caption) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/ui/test_cost_badge.py -m ui -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui.components.cost_badge'`

- [ ] **Step 3: Write the component**

```python
"""Renders what one diagnosis cost, in tokens and money."""

import streamlit as st


def render_cost_badge(token_usage: dict[str, int] | None, cost_usd: float | None) -> None:
    """Render a one-line usage caption, or nothing at all.

    Renders nothing when no usage was recorded — every diagnosis written before
    Phase 3 has NULL columns, and a "0 tokens" badge would misreport those as free
    rather than as unmeasured. Cost is omitted on the same principle when the
    provider reported none (spec §5).
    """
    if not token_usage:
        return

    prompt = token_usage.get("prompt_tokens", 0)
    completion = token_usage.get("completion_tokens", 0)
    parts = [f"{prompt:,} in / {completion:,} out tokens"]
    if cost_usd is not None:
        parts.append(f"${cost_usd:.4f}")
    st.caption(" · ".join(parts))
```

- [ ] **Step 4: Render it in both places**

In `ui/components/timeline.py`, import the component and add one line as the last statement of the per-diagnosis `with st.container(border=True):` block, after the reasoning caption:

```python
from ui.components.cost_badge import render_cost_badge
```

```python
            st.caption(diagnosis.differential.reasoning)
            render_cost_badge(diagnosis.token_usage, diagnosis.cost_usd)
```

In `ui/pages/diagnose.py`, find where the completed `FinalResult` is rendered — the block that renders the differential and roadmap after `service.answer(...)` returns — and add the badge as the last line of that block, reading the two fields Task 6 Step 5 added:

```python
from ui.components.cost_badge import render_cost_badge
```

```python
    render_cost_badge(result.token_usage, result.cost_usd)
```

`result` is the `FinalResult` already in scope; no repository read and no new import beyond the component.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest -m ui -v` then `uv run pytest`
Expected: PASS both.

- [ ] **Step 6: Record `M12` resolved and chat cost as a new gap**

In `docs/known-limitations.md`, strike through `M12`'s heading and append the resolution, matching the format used for `M10` and `U7`:

```markdown
| M12 | **~~`token_usage_json` and `cost_usd` are never written at all.~~** *Resolved 2026-08-13 (Phase 3) — a run-scoped `UsageCollector` (`core/cost.py`) is attached to every graph invoke as a callback and read by `persist` inside its existing transaction. Cost comes from OpenRouter's reported usage rather than a price table.* | Fixed. | ✓ Complete |
```

Add a new row for the gap this phase deliberately creates:

```markdown
| M17 | **Chat token usage and cost are not tracked.** The `messages` table has no usage columns, and adding them would require the project's first schema migration — against the property Phase 2 deliberately preserved by building the whole schema up front. Diagnosis runs *are* tracked (`M12`). | Chat spend is small next to a vision-plus-reasoning diagnosis, and the Medium 1 claim is satisfied by diagnosis cost. Recorded rather than left silent. | Add `token_usage_json`/`cost_usd` to `messages` together with an `ALTER TABLE` migration path in `data/db.py`, and give `ChatService` the same thread-scoped collector `DiagnosisService` uses. |
```

Update the "Deliberate non-goals" bullet that reads "Phase 2 and Phase 3 scope … is planned, not missing" to name only what remains: the learned user profile, now Phase 4.

In `README.md`, add LangSmith to whatever configuration/optional-keys section exists, phrased like the existing Tavily entry.

- [ ] **Step 7: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add ui/ docs/known-limitations.md README.md tests/ui/test_cost_badge.py
git commit -m "feat: show token usage and cost per diagnosis"
```

**Block A is complete and independently shippable at this point.**

---

# Block B — Evaluation

## Task 8: Golden-case schema, loader, and the first three cases

**Files:**
- Modify: `pyproject.toml`
- Create: `eval/__init__.py`, `eval/cases.py`, `eval/golden_set/{overwatering-lower-leaf-yellowing,spider-mites-stippling-webbing,insufficient-light-etiolation}.yaml`
- Test: `tests/unit/eval/test_cases.py`

**Interfaces:**
- Produces:
  - `GoldenCase` (Pydantic) with `id, category, plant, species_confidence, symptoms: SymptomSet, answers: dict[str, str], default_answer: str, ground_truth: str, also_acceptable: list[str]`
  - `CasePlant` with `name: str, species: str | None, location_kind: Literal["indoor","outdoor"], location_text: str | None`
  - `load_cases(directory: Path) -> list[GoldenCase]`
  - `corpus_slugs(corpus_dir: Path) -> set[str]`
  - `CATEGORIES: frozenset[str]`

- [ ] **Step 1: Add the dependencies and coverage config**

```bash
uv add --dev ragas pyyaml
```

In `pyproject.toml`, extend `[tool.coverage.run] source` and `omit`:

```toml
source = ["core", "agent", "tools", "data", "knowledge", "services", "ui", "eval"]
```

and append to `omit`, after the `ui/components/*` entry:

```toml
    # The evaluation CLI: argument parsing, real model construction and file writing,
    # on ui/bootstrap.py's precedent. Everything beneath it — case loading, the
    # scripted model, scoring, stability, report rendering — is unit-tested.
    "eval/run_eval.py",
```

- [ ] **Step 2: Write the failing tests**

```python
"""Unit tests for the golden-set schema and loader."""

from pathlib import Path

import pytest

from eval.cases import CATEGORIES, GoldenCase, corpus_slugs, load_cases

GOLDEN_SET = Path("eval/golden_set")
CORPUS = Path("knowledge/corpus")


def test_every_case_parses():
    cases = load_cases(GOLDEN_SET)
    assert cases, "the golden set is empty"
    assert all(isinstance(case, GoldenCase) for case in cases)


def test_case_ids_are_unique():
    ids = [case.id for case in load_cases(GOLDEN_SET)]
    assert len(ids) == len(set(ids))


def test_every_ground_truth_resolves_to_a_corpus_document():
    """A case naming a disorder the corpus does not contain would score zero at
    runtime for a reason that has nothing to do with agent quality (spec §6)."""
    slugs = corpus_slugs(CORPUS)
    unknown = {
        case.id: case.ground_truth
        for case in load_cases(GOLDEN_SET)
        if case.ground_truth not in slugs
    }
    assert not unknown, f"ground_truth not in corpus: {unknown}"


def test_every_alternative_resolves_to_a_corpus_document():
    slugs = corpus_slugs(CORPUS)
    unknown = {
        case.id: sorted(set(case.also_acceptable) - slugs)
        for case in load_cases(GOLDEN_SET)
        if set(case.also_acceptable) - slugs
    }
    assert not unknown, f"also_acceptable not in corpus: {unknown}"


def test_ground_truth_is_not_repeated_in_alternatives():
    offenders = [
        case.id for case in load_cases(GOLDEN_SET) if case.ground_truth in case.also_acceptable
    ]
    assert not offenders


def test_every_category_is_from_the_fixed_vocabulary():
    for case in load_cases(GOLDEN_SET):
        assert case.category in CATEGORIES


def test_a_malformed_case_names_the_file(tmp_path):
    """Fail at the suite, not at runtime — the philosophy test_corpus_coverage uses."""
    bad = tmp_path / "broken.yaml"
    bad.write_text("id: broken\ncategory: watering\n", encoding="utf-8")

    with pytest.raises(ValueError, match="broken.yaml"):
        load_cases(tmp_path)


def test_an_empty_directory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no golden cases"):
        load_cases(tmp_path)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/eval/test_cases.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.cases'`

- [ ] **Step 4: Write `eval/cases.py`**

```python
"""The golden set: schema, loader, and corpus cross-checking.

Cases are text, not photographs. Every Ragas metric except top-1/top-3 is a
retrieval-and-generation metric that cannot see the vision layer, and the public
leaf-disease datasets ``PLAN.md`` §16 proposed are crop pathology while this corpus
is houseplant disorders — so scoring against them would measure corpus scope rather
than agent quality (spec §3.1). The price is that vision accuracy goes unmeasured,
which the report states rather than hides.

One YAML file per case, mirroring the corpus's one-document-per-disorder layout so
cases diff and review individually.
"""

from pathlib import Path
from typing import Literal

import frontmatter
import yaml
from pydantic import BaseModel, Field, ValidationError

from agent.schemas import SymptomSet

CATEGORIES: frozenset[str] = frozenset(
    {"watering", "light", "nutrient", "pest", "fungal", "environmental", "other"}
)


class CasePlant(BaseModel):
    """The plant record a case implies, standing in for one the user would have."""

    name: str = Field(min_length=1)
    species: str | None = None
    location_kind: Literal["indoor", "outdoor"] = "indoor"
    location_text: str | None = None


class GoldenCase(BaseModel):
    """One evaluation case: a situation, its pre-written answers, and the truth."""

    id: str = Field(min_length=1)
    category: str
    plant: CasePlant
    species_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    symptoms: SymptomSet
    answers: dict[str, str] = Field(default_factory=dict)
    # Clarifying questions are model-generated, so the set asked varies between runs
    # of the same case. Anything unmatched gets this rather than being left blank,
    # and the harness records which questions were actually asked (spec §3.4).
    default_answer: str = "not observed"
    ground_truth: str = Field(min_length=1)
    also_acceptable: list[str] = Field(default_factory=list)


def corpus_slugs(corpus_dir: Path) -> set[str]:
    """Every disorder id in the corpus, read from document frontmatter."""
    return {
        str(frontmatter.loads(path.read_text(encoding="utf-8"))["id"])
        for path in sorted(corpus_dir.glob("*.md"))
    }


def load_cases(directory: Path) -> list[GoldenCase]:
    """Parse every golden case in a directory, sorted by id.

    Raises:
        ValueError: if the directory holds no cases, or any case is malformed. The
            message names the file — a case that fails to parse must fail the suite
            rather than silently drop out of a metrics run.
    """
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise ValueError(f"no golden cases found in {directory}")

    cases: list[GoldenCase] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            cases.append(GoldenCase.model_validate(raw))
        except ValidationError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
    return sorted(cases, key=lambda case: case.id)
```

- [ ] **Step 5: Write the first three cases**

`eval/golden_set/overwatering-lower-leaf-yellowing.yaml`:

```yaml
id: overwatering-lower-leaf-yellowing
category: watering
plant:
  name: "Kitchen ficus"
  species: "Ficus elastica"
  location_kind: indoor
species_confidence: 0.82
symptoms:
  overall_vigor: declining
  soil_condition: "wet and dense, still damp a week after watering"
  symptoms:
    - description: "uniform yellowing of the oldest leaves"
      position: lower_leaves
      severity: act_this_week
    - description: "soft brown patches spreading from the leaf base"
      position: whole_leaf
      severity: act_this_week
answers:
  drainage: "the pot has no drainage holes"
  watering_frequency: "twice a week, on a schedule"
  light_hours: "about four hours of indirect light"
default_answer: "not observed"
ground_truth: overwatering
also_acceptable:
  - poor-drainage
  - root-rot
```

`eval/golden_set/spider-mites-stippling-webbing.yaml`:

```yaml
id: spider-mites-stippling-webbing
category: pest
plant:
  name: "Living room calathea"
  species: "Calathea orbifolia"
  location_kind: indoor
species_confidence: 0.75
symptoms:
  overall_vigor: declining
  soil_condition: "evenly moist, drains freely"
  symptoms:
    - description: "fine pale stippling across the upper leaf surface"
      position: whole_leaf
      severity: act_this_week
    - description: "faint webbing in the leaf axils"
      position: stem
      severity: act_today
answers:
  drainage: "the pot drains freely"
  recent_changes: "nothing new, but the radiator has been on"
  humidity: "dry, the room is heated"
default_answer: "not observed"
ground_truth: spider-mites
also_acceptable:
  - thrips
  - low-humidity
```

`eval/golden_set/insufficient-light-etiolation.yaml`:

```yaml
id: insufficient-light-etiolation
category: light
plant:
  name: "Bedroom succulent"
  species: "Echeveria elegans"
  location_kind: indoor
species_confidence: 0.68
symptoms:
  overall_vigor: declining
  soil_condition: "dry, drains quickly"
  symptoms:
    - description: "stem stretched with widely spaced leaves"
      position: whole_plant
      severity: monitor
    - description: "pale, washed-out new growth leaning toward the window"
      position: new_growth
      severity: monitor
answers:
  light_hours: "maybe two hours, north-facing window"
  watering_frequency: "every three weeks"
  drainage: "the pot drains freely"
default_answer: "not observed"
ground_truth: insufficient-light
also_acceptable:
  - etiolation
```

> **Before committing, confirm each `ground_truth` and `also_acceptable` slug exists:**
> `ls knowledge/corpus/ | sed 's/\.md$//'`. The tests enforce this, but reading the list first is faster than a red suite.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add pyproject.toml uv.lock eval/ tests/unit/eval/
git commit -m "feat: add the golden-case schema, loader, and first three cases"
```

---

## Task 9: Author the golden set to 25–30 cases

Content work, not code. The structural tests from Task 8 are the gate.

**Files:**
- Create: `eval/golden_set/*.yaml` (22–27 more)
- Modify: `tests/unit/eval/test_cases.py`

**Interfaces:**
- Consumes: `GoldenCase` from Task 8.
- Produces: a golden set large enough for per-category reporting.

- [ ] **Step 1: Write the failing size and coverage tests**

```python
def test_the_golden_set_is_large_enough():
    """PLAN.md §16 specifies 25-30 cases."""
    assert 25 <= len(load_cases(GOLDEN_SET)) <= 30


def test_every_category_has_at_least_two_cases():
    """Per-category breakdowns are the point of the category field; a category with
    one case reports a meaningless 0% or 100%."""
    from collections import Counter

    counts = Counter(case.category for case in load_cases(GOLDEN_SET))
    thin = {category: n for category, n in counts.items() if n < 2}
    assert not thin, f"categories with fewer than two cases: {thin}"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_cases.py -v -k "large_enough or category_has"`
Expected: FAIL — 3 cases, not 25.

- [ ] **Step 3: Author the remaining cases**

Target distribution, chosen so failure can be located rather than merely observed — `PLAN.md` §16 predicts failure concentrates among nutrient deficiencies, so they get the largest share:

| Category | Cases | Draw `ground_truth` from |
|---|---|---|
| watering | 4 | `overwatering`, `underwatering`, `poor-drainage`, `root-rot` |
| nutrient | 6 | `nitrogen-deficiency`, `iron-deficiency`, `magnesium-deficiency`, `potassium-deficiency`, `phosphorus-deficiency`, `calcium-deficiency` |
| pest | 5 | `spider-mites`, `aphids`, `mealybugs`, `fungus-gnats`, `scale-insects` |
| fungal | 4 | `powdery-mildew`, `botrytis`, `fungal-leaf-spot`, `rust` |
| light | 3 | `insufficient-light`, `etiolation`, `sunscald` |
| environmental | 4 | `low-humidity`, `heat-stress`, `cold-draught`, `salt-buildup` |
| other | 2 | `natural-senescence`, `pot-bound` |

Rules for authoring, each with a reason:

1. **Write the symptoms from the corpus document's "Symptoms" and "Where on the plant symptoms appear" sections, then close the file and paraphrase.** Copying its wording verbatim would let retrieval match on shared phrasing rather than on meaning, inflating context recall.
2. **Always populate `drainage`** — it is the one mandatory clarifying question, so it is asked on every run.
3. **Set `also_acceptable` to genuinely confusable neighbours only**, taken from the document's "Look-alikes and how to tell them apart" section. It is not a safety net for a weak case.
4. **Vary `location_kind`.** At least three outdoor cases, so the weather tool path is exercised; give those a `location_text` such as `"Berlin"`.
5. **Include at least one case whose honest answer is `natural-senescence`** — a healthy-enough plant losing an old leaf. `Differential.is_healthy` is a valid outcome and the agent must not manufacture a problem (`PLAN.md` §14).
6. **Give each case 2–4 symptoms.** One is too thin to discriminate; five reads as a symptom checklist rather than a photograph.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS — all cases parse, slugs resolve, categories are populated.

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/golden_set/ tests/unit/eval/test_cases.py
git commit -m "feat: author the golden set to 28 cases across seven categories"
```

---

## Task 10: The schema-dispatching scripted model

**Files:**
- Create: `eval/scripted.py`
- Test: `tests/unit/eval/test_scripted.py`

**Interfaces:**
- Consumes: `GoldenCase` from Task 8.
- Produces: `case_models(case: GoldenCase) -> tuple[BaseChatModel, BaseChatModel]` returning `(gate, vision)`; `SchemaDispatchModel(case=...)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the schema-dispatching evaluation model."""

from agent.schemas import ImageQuality, PlantCheck, SpeciesGuess, SymptomSet
from eval.cases import GoldenCase
from eval.scripted import SchemaDispatchModel, case_models


def _case() -> GoldenCase:
    return GoldenCase.model_validate(
        {
            "id": "t",
            "category": "watering",
            "plant": {"name": "Test", "species": "Ficus elastica"},
            "species_confidence": 0.9,
            "symptoms": {
                "overall_vigor": "declining",
                "soil_condition": "wet",
                "symptoms": [
                    {
                        "description": "yellowing lower leaves",
                        "position": "lower_leaves",
                        "severity": "act_this_week",
                    }
                ],
            },
            "ground_truth": "overwatering",
        }
    )


def test_dispatch_is_independent_of_call_order():
    """route_after_quality branches, so a positional queue desynchronises (spec §3.3)."""
    model = SchemaDispatchModel(case=_case())

    symptoms = model.with_structured_output(SymptomSet).invoke("prompt")
    species = model.with_structured_output(SpeciesGuess).invoke("prompt")

    assert species.common_name == "Ficus elastica"
    assert symptoms.symptoms[0].position.value == "lower_leaves"


def test_the_same_schema_can_be_requested_twice():
    """A re-check may identify a plant a second time; a queue would be exhausted."""
    model = SchemaDispatchModel(case=_case())

    first = model.with_structured_output(SpeciesGuess).invoke("p")
    second = model.with_structured_output(SpeciesGuess).invoke("p")

    assert first == second


def test_the_guards_pass():
    model = SchemaDispatchModel(case=_case())

    assert model.with_structured_output(PlantCheck).invoke("p").is_plant is True
    assert model.with_structured_output(ImageQuality).invoke("p").usable is True


def test_species_confidence_comes_from_the_case():
    model = SchemaDispatchModel(case=_case())

    assert model.with_structured_output(SpeciesGuess).invoke("p").confidence == 0.9


def test_a_case_without_a_species_still_identifies():
    """A blank species must not produce an empty common_name, which SpeciesGuess rejects."""
    raw = _case().model_dump()
    raw["plant"]["species"] = None
    model = SchemaDispatchModel(case=GoldenCase.model_validate(raw))

    guess = model.with_structured_output(SpeciesGuess).invoke("p")
    assert guess.common_name
    assert guess.confidence == 0.0


def test_an_unknown_schema_raises():
    """Silence here would mean a node quietly received nothing at all."""
    from pydantic import BaseModel

    class Unknown(BaseModel):
        pass

    model = SchemaDispatchModel(case=_case())

    try:
        model.with_structured_output(Unknown).invoke("p")
    except ValueError as exc:
        assert "Unknown" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_case_models_returns_a_gate_and_a_vision_tier():
    gate, vision = case_models(_case())

    assert gate.with_structured_output(PlantCheck).invoke("p").is_plant is True
    assert vision.with_structured_output(SpeciesGuess).invoke("p").common_name == "Ficus elastica"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_scripted.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.scripted'`

- [ ] **Step 3: Write `eval/scripted.py`**

```python
"""A scripted model that answers by schema, not by call order.

Deliberately unlike ``tests/fakes/chat_models.py``'s ``ScriptedStructuredModel``,
which replays a positional queue. ``route_after_quality`` branches — a re-check of
an unidentified plant calls ``identify_plant``, a fresh diagnosis may not — and a
positional queue desynchronises on the branch, returning a ``SymptomSet`` where a
``SpeciesGuess`` was asked for. Dispatching on the requested schema is
order-independent and re-entrant (spec §3.3).

Keeping this here rather than importing the test fake also keeps the dependency
direction right: nothing outside ``tests/`` should import from it.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict

from agent.schemas import ImageQuality, PlantCheck, SpeciesGuess, SymptomSet
from eval.cases import GoldenCase


def _response_for(schema: Any, case: GoldenCase) -> BaseModel:
    """The canned object a node asking for ``schema`` should receive."""
    if schema is PlantCheck:
        return PlantCheck(is_plant=True, what_it_is=f"a {case.plant.name}")
    if schema is ImageQuality:
        return ImageQuality(usable=True, problem=None, guidance=None)
    if schema is SpeciesGuess:
        # An unidentified plant is a real case (a re-check routes through
        # identify_plant precisely to fix one), but common_name has min_length=1,
        # so the unknown case is expressed as zero confidence rather than an
        # empty string the schema would reject.
        if case.plant.species:
            return SpeciesGuess(
                common_name=case.plant.species,
                scientific_name=None,
                confidence=case.species_confidence,
            )
        return SpeciesGuess(common_name="Unidentified plant", scientific_name=None, confidence=0.0)
    if schema is SymptomSet:
        return case.symptoms
    raise ValueError(
        f"no scripted response for schema {getattr(schema, '__name__', schema)!r}. "
        "The evaluation harness only scripts the gate and vision tiers; the "
        "reasoning tier must be a real model."
    )


class SchemaDispatchModel(BaseChatModel):
    """Answers ``with_structured_output`` from a golden case, keyed by schema."""

    case: GoldenCase
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "schema-dispatch"

    def _generate(self, messages: list, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("use with_structured_output")

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        case = self.case
        return RunnableLambda(lambda _prompt: _response_for(schema, case))


def case_models(case: GoldenCase) -> tuple[BaseChatModel, BaseChatModel]:
    """The ``(gate, vision)`` tiers for one case.

    Two instances rather than one shared: ``Deps`` holds the tiers separately, and
    keeping them distinct means a future change to one cannot silently affect the
    other.
    """
    return SchemaDispatchModel(case=case), SchemaDispatchModel(case=case)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/scripted.py tests/unit/eval/test_scripted.py
git commit -m "feat: add the schema-dispatching model for evaluation runs"
```

---

## Task 11: The harness — run one case

**Files:**
- Create: `eval/harness.py`
- Test: `tests/unit/eval/test_harness.py`

**Interfaces:**
- Consumes: `GoldenCase`, `case_models`, `UsageCollector`.
- Produces:
  - `CaseRun(case_id, ground_truth, category, candidates: list[str], reasoning: str, contexts: list[str], questions_asked: list[str], usage: UsageSnapshot | None, error: str | None)`
  - `run_case(case, *, deps, graph, thread_id) -> CaseRun`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the evaluation harness, using scripted models throughout."""

from eval.cases import GoldenCase
from eval.harness import CaseRun, run_case


def test_a_completed_run_reports_ranked_candidates(make_deps, pipeline_models, golden_case):
    """The reasoning tier stays scripted here so this test needs no network."""
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)
    graph = _build_graph(deps)

    run = run_case(golden_case, deps=deps, graph=graph, thread_id="eval-1")

    assert run.candidates == ["overwatering", "root-rot"]
    assert run.error is None
    assert run.reasoning


def test_the_questions_asked_are_recorded(make_deps, pipeline_models, golden_case):
    """Question drift is itself a variance source and must be separable from it
    in the stability numbers (spec §3.4)."""
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-2")

    assert run.questions_asked == ["light_hours"]


def test_retrieved_passages_become_contexts(make_deps, pipeline_models, golden_case):
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-3")

    assert all(isinstance(context, str) for context in run.contexts)


def test_a_failing_run_is_recorded_not_raised(make_deps, golden_case):
    """One bad case must not abort a 30-case run (spec §5)."""
    from tests.fakes.chat_models import FailingChatModel

    deps = make_deps(chat_model=FailingChatModel(RuntimeError("boom")))

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-4")

    assert isinstance(run, CaseRun)
    assert run.error is not None
    assert run.candidates == []


def test_the_case_metadata_is_carried_through(make_deps, pipeline_models, golden_case):
    gate, vision, chat = pipeline_models
    deps = make_deps(gate_model=gate, vision_model=vision, chat_model=chat)

    run = run_case(golden_case, deps=deps, graph=_build_graph(deps), thread_id="eval-5")

    assert run.case_id == golden_case.id
    assert run.ground_truth == "overwatering"
    assert run.category == "watering"
```

Add to `tests/unit/eval/conftest.py`:

```python
"""Fixtures for evaluation tests."""

import pytest

from eval.cases import GoldenCase


@pytest.fixture
def golden_case() -> GoldenCase:
    """A case whose ground truth matches what `pipeline_models` is scripted to return."""
    return GoldenCase.model_validate(
        {
            "id": "overwatering-test",
            "category": "watering",
            "plant": {"name": "Kitchen basil", "species": "Basil"},
            "species_confidence": 0.9,
            "symptoms": {
                "overall_vigor": "declining",
                "soil_condition": "wet",
                "symptoms": [
                    {
                        "description": "yellowing lower leaves",
                        "position": "lower_leaves",
                        "severity": "act_this_week",
                    }
                ],
            },
            "answers": {"light_hours": "four hours indirect"},
            "ground_truth": "overwatering",
            "also_acceptable": ["root-rot"],
        }
    )
```

Define `_build_graph` at the top of the test module:

```python
def _build_graph(deps):
    """The real graph with an in-memory checkpointer, as tests/graph/ builds it."""
    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph

    return build_diagnosis_graph(deps, MemorySaver())
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.harness'`

- [ ] **Step 3: Write `eval/harness.py`**

```python
"""Run one golden case through the real diagnosis graph.

Only the gate and vision tiers are scripted (``eval/scripted.py``). The reasoning
model, the retriever, the corpus, the graph, and the interrupt are all real — this
measures retrieval and differential reasoning, which is exactly what the Ragas
metrics can see (spec §3.1).
"""

import logging
from dataclasses import dataclass

from langgraph.types import Command

from agent.deps import Deps
from agent.state import DiagnosisState
from core.cost import UsageCollector, UsageSnapshot
from eval.cases import GoldenCase

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CaseRun:
    """What one pass over one case produced."""

    case_id: str
    ground_truth: str
    category: str
    candidates: list[str]
    reasoning: str
    contexts: list[str]
    questions_asked: list[str]
    usage: UsageSnapshot | None
    error: str | None = None


def _answers_for(case: GoldenCase, questions: list) -> dict[str, str]:
    """Answer every question asked, falling back for ones the case did not foresee."""
    return {
        question.key: case.answers.get(question.key, case.default_answer)
        for question in questions
    }


def run_case(case: GoldenCase, *, deps: Deps, graph, thread_id: str) -> CaseRun:
    """Run one case end to end. Never raises — a failure becomes a recorded row.

    A single bad case must not abort a thirty-case run (spec §5), so every
    exception is caught and reported as data.
    """
    collector = UsageCollector()
    config = {
        "configurable": {"thread_id": thread_id, "usage_collector": collector},
        "callbacks": [collector],
    }

    def _failed(message: str) -> CaseRun:
        return CaseRun(
            case_id=case.id,
            ground_truth=case.ground_truth,
            category=case.category,
            candidates=[],
            reasoning="",
            contexts=[],
            questions_asked=[],
            usage=collector.snapshot(),
            error=message,
        )

    try:
        state = DiagnosisState(
            images=[],
            plant_name=case.plant.name,
            location_kind=case.plant.location_kind,
            location_text=case.plant.location_text,
            user_notes=None,
        )
        started = graph.invoke(state, config)

        questions_asked: list[str] = []
        interrupts = started.get("__interrupt__") or []
        if interrupts:
            from agent.schemas import Question

            questions = [Question.model_validate(q) for q in interrupts[0].value["questions"]]
            questions_asked = [question.key for question in questions]
            result = graph.invoke(Command(resume=_answers_for(case, questions)), config)
        else:
            result = started

        differential = result.get("differential")
        if differential is None:
            return _failed("the run produced no differential")

        return CaseRun(
            case_id=case.id,
            ground_truth=case.ground_truth,
            category=case.category,
            candidates=[candidate.disorder_id for candidate in differential.candidates],
            reasoning=differential.reasoning,
            contexts=[passage.text for passage in result.get("retrieved") or []],
            questions_asked=questions_asked,
            usage=collector.snapshot(),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 — a failed case is data, not a crash
        logger.warning("case %s failed: %s", case.id, exc)
        return _failed(f"{type(exc).__name__}: {exc}")
```

> **Note on images.** `DiagnosisState.images` is empty, so the gate and quality nodes have no image to inspect — which is why they are scripted to pass unconditionally. If a guard node short-circuits on an empty image list before consulting its model, adjust that node's *test seam* rather than the node: pass a single tiny `ImageRef` exactly like `tests/conftest.py`'s `sample_images` fixture does.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/harness.py tests/unit/eval/
git commit -m "feat: add the evaluation harness for a single golden case"
```

---

## Task 12: Accuracy and stability metrics

**Files:**
- Create: `eval/metrics.py`
- Test: `tests/unit/eval/test_metrics.py`

**Interfaces:**
- Consumes: `CaseRun` from Task 11.
- Produces: `top1_hit`, `top3_hit`, `accuracy(runs) -> AccuracyReport`, `stability(runs_by_case) -> StabilityReport`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for accuracy and stability scoring. Pure functions, no network."""

from eval.harness import CaseRun
from eval.metrics import accuracy, stability, top1_hit, top3_hit


def _run(case_id: str, candidates: list[str], truth: str = "overwatering", **kw) -> CaseRun:
    return CaseRun(
        case_id=case_id,
        ground_truth=truth,
        category=kw.pop("category", "watering"),
        candidates=candidates,
        reasoning="because",
        contexts=[],
        questions_asked=kw.pop("questions_asked", []),
        usage=None,
        error=kw.pop("error", None),
    )


def test_top1_hit_on_an_exact_match():
    assert top1_hit(_run("a", ["overwatering", "root-rot"])) is True


def test_top1_miss_when_the_truth_is_second():
    assert top1_hit(_run("a", ["root-rot", "overwatering"])) is False


def test_top3_hit_when_the_truth_is_third():
    assert top3_hit(_run("a", ["rust", "root-rot", "overwatering"])) is True


def test_top3_miss_when_the_truth_is_fourth():
    assert top3_hit(_run("a", ["rust", "root-rot", "aphids", "overwatering"])) is False


def test_an_empty_differential_is_a_miss():
    assert top1_hit(_run("a", [])) is False
    assert top3_hit(_run("a", [])) is False


def test_accuracy_aggregates_and_breaks_down_by_category():
    runs = [
        _run("a", ["overwatering"], category="watering"),
        _run("b", ["root-rot"], category="watering"),
        _run("c", ["aphids"], truth="aphids", category="pest"),
    ]

    report = accuracy(runs)

    assert report.top1 == 2 / 3
    assert report.by_category["watering"].top1 == 0.5
    assert report.by_category["pest"].top1 == 1.0


def test_failed_runs_are_counted_but_never_silently_dropped():
    """Averaging over survivors would flatter the result (spec §5)."""
    runs = [_run("a", ["overwatering"]), _run("b", [], error="boom")]

    report = accuracy(runs)

    assert report.failed == 1
    assert report.scored == 2
    assert report.top1 == 0.5


def test_accuracy_of_no_runs_is_zero_not_a_division_error():
    report = accuracy([])
    assert report.top1 == 0.0
    assert report.scored == 0


def test_stability_is_one_when_every_repeat_agrees():
    runs = {"a": [_run("a", ["overwatering"]) for _ in range(5)]}

    report = stability(runs)

    assert report.top1_agreement == 1.0
    assert report.candidate_churn == 0.0


def test_stability_falls_when_the_top_candidate_moves():
    runs = {
        "a": [
            _run("a", ["overwatering", "root-rot"]),
            _run("a", ["overwatering", "root-rot"]),
            _run("a", ["rust", "root-rot"]),
        ]
    }

    report = stability(runs)

    assert report.top1_agreement == 2 / 3
    assert report.candidate_churn > 0.0


def test_churn_is_total_when_candidate_sets_are_disjoint():
    """The recorded finding: Root Rot 60% one run, Rust 60% the next."""
    runs = {
        "a": [
            _run("a", ["root-rot", "insufficient-light", "magnesium-deficiency"]),
            _run("a", ["rust", "fungal-leaf-spot", "natural-senescence"]),
        ]
    }

    report = stability(runs)

    assert report.candidate_churn == 1.0
    assert report.top1_agreement == 0.5


def test_question_drift_is_reported_separately_from_variance():
    runs = {
        "a": [
            _run("a", ["overwatering"], questions_asked=["drainage", "light_hours"]),
            _run("a", ["overwatering"], questions_asked=["drainage", "humidity"]),
        ]
    }

    report = stability(runs)

    assert report.question_drift > 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.metrics'`

- [ ] **Step 3: Write `eval/metrics.py`**

```python
"""Diagnostic accuracy and run-to-run stability.

Pure functions over ``CaseRun`` objects — no network, no models — so the scoring
itself is fully unit-tested. Ragas metrics live in ``eval/ragas_metrics.py``
precisely so that this module stays offline and deterministic.
"""

from dataclasses import dataclass, field
from itertools import combinations

from eval.harness import CaseRun


def _accepted(run: CaseRun) -> set[str]:
    """The disorder ids that count as correct for this case."""
    return {run.ground_truth}


def top1_hit(run: CaseRun) -> bool:
    """Was the leading candidate the ground truth?"""
    return bool(run.candidates) and run.candidates[0] in _accepted(run)


def top3_hit(run: CaseRun) -> bool:
    """Was the ground truth anywhere in the top three?

    Reported alongside top-1 because the gap between them locates the weakness: a
    high top-3 with a mediocre top-1 says ranking is the problem, not retrieval
    (``PLAN.md`` §16).
    """
    return bool(_accepted(run) & set(run.candidates[:3]))


@dataclass(frozen=True, slots=True)
class Scores:
    top1: float
    top3: float
    scored: int


@dataclass(frozen=True, slots=True)
class AccuracyReport:
    top1: float
    top3: float
    scored: int
    failed: int
    by_category: dict[str, Scores] = field(default_factory=dict)


def _score(runs: list[CaseRun]) -> Scores:
    if not runs:
        return Scores(top1=0.0, top3=0.0, scored=0)
    return Scores(
        top1=sum(top1_hit(run) for run in runs) / len(runs),
        top3=sum(top3_hit(run) for run in runs) / len(runs),
        scored=len(runs),
    )


def accuracy(runs: list[CaseRun]) -> AccuracyReport:
    """Overall and per-category accuracy.

    Failed runs stay in the denominator. Averaging over the survivors would report
    a better number for a worse run, which is the opposite of what an evaluation is
    for (spec §5).
    """
    overall = _score(runs)
    categories: dict[str, list[CaseRun]] = {}
    for run in runs:
        categories.setdefault(run.category, []).append(run)

    return AccuracyReport(
        top1=overall.top1,
        top3=overall.top3,
        scored=len(runs),
        failed=sum(1 for run in runs if run.error is not None),
        by_category={name: _score(group) for name, group in sorted(categories.items())},
    )


@dataclass(frozen=True, slots=True)
class StabilityReport:
    """How much the same input moves the answer.

    ``top1_agreement`` is the share of repeats landing on the modal top candidate.
    ``candidate_churn`` is mean pairwise Jaccard *distance* between candidate sets:
    0.0 is identical, 1.0 disjoint. ``question_drift`` is the same distance over
    the clarifying questions asked, reported separately because questions are
    model-generated and their variance would otherwise be read as diagnostic
    instability (spec §3.4).
    """

    top1_agreement: float
    candidate_churn: float
    question_drift: float
    cases: int
    runs_per_case: float


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return 1.0 - len(left & right) / len(union)


def _mean_pairwise_distance(sets: list[set[str]]) -> float:
    pairs = list(combinations(sets, 2))
    if not pairs:
        return 0.0
    return sum(_jaccard_distance(a, b) for a, b in pairs) / len(pairs)


def _modal_agreement(tops: list[str | None]) -> float:
    """Share of runs landing on the modal top candidate.

    ``tops`` holds one entry per run, ``None`` where the run had no candidates (a
    failed run). The denominator is always ``len(tops)`` — every run, failed or
    not. A failed run can never agree with anything, so it contributes to the
    denominator but never to the modal count. Dropping it from both instead would
    let a failure vanish from the very number meant to measure instability: three
    runs where two agree and one fails would report 1.0, not 2/3. That is the same
    "average over the survivors" mistake this plan forbids for ``accuracy()``.
    """
    if not tops:
        return 0.0
    hits = [value for value in tops if value is not None]
    if not hits:
        return 0.0
    return max(hits.count(value) for value in set(hits)) / len(tops)


def stability(runs_by_case: dict[str, list[CaseRun]]) -> StabilityReport:
    """Aggregate variance across repeated runs of the same cases."""
    if not runs_by_case:
        return StabilityReport(0.0, 0.0, 0.0, cases=0, runs_per_case=0.0)

    agreements, churns, drifts = [], [], []
    for runs in runs_by_case.values():
        agreements.append(
            _modal_agreement([r.candidates[0] if r.candidates else None for r in runs])
        )
        churns.append(_mean_pairwise_distance([set(r.candidates) for r in runs]))
        drifts.append(_mean_pairwise_distance([set(r.questions_asked) for r in runs]))

    total_runs = sum(len(runs) for runs in runs_by_case.values())
    return StabilityReport(
        top1_agreement=sum(agreements) / len(agreements),
        candidate_churn=sum(churns) / len(churns),
        question_drift=sum(drifts) / len(drifts),
        cases=len(runs_by_case),
        runs_per_case=total_runs / len(runs_by_case),
    )
```

> **Design note for the implementer.** `_accepted()` deliberately ignores `also_acceptable` for the headline numbers — a near miss is still a miss, and treating confusable neighbours as correct would flatter exactly the cases `PLAN.md` §16 predicts are hardest. The field is reported separately by `eval/report.py` (Task 14) as a "near miss" count. Do not fold it into `top1_hit`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/metrics.py tests/unit/eval/test_metrics.py
git commit -m "feat: add accuracy and run-to-run stability scoring"
```

---

## Task 13: Ragas metrics, isolated

**Files:**
- Create: `eval/ragas_metrics.py`
- Test: `tests/unit/eval/test_ragas_metrics.py`

**Interfaces:**
- Consumes: `CaseRun`; `build_reasoning_model`, `build_embeddings` from `core/llm.py`.
- Produces: `to_ragas_rows(runs) -> list[dict]`; `evaluate_runs(runs, *, llm=None, embeddings=None) -> dict[str, float | None]`

- [ ] **Step 1: Write the failing tests**

Only the row mapping and the failure handling are unit-tested — a real Ragas evaluation is a network call and belongs to the CLI.

```python
"""Unit tests for the Ragas adapter. The evaluation call itself is not exercised here."""

from eval.harness import CaseRun
from eval.ragas_metrics import evaluate_runs, to_ragas_rows


def _run(**kw) -> CaseRun:
    defaults = {
        "case_id": "a",
        "ground_truth": "overwatering",
        "category": "watering",
        "candidates": ["overwatering"],
        "reasoning": "Wet soil and lower-leaf yellowing.",
        "contexts": ["Overwatering: soil stays wet for days."],
        "questions_asked": ["drainage"],
        "usage": None,
        "error": None,
    }
    return CaseRun(**{**defaults, **kw})


def test_rows_carry_the_four_fields_ragas_needs():
    rows = to_ragas_rows([_run()])

    assert set(rows[0]) == {"user_input", "response", "retrieved_contexts", "reference"}
    assert rows[0]["retrieved_contexts"] == ["Overwatering: soil stays wet for days."]
    assert rows[0]["reference"] == "overwatering"


def test_failed_runs_are_excluded_from_the_rows():
    """A run with no differential has no response to score."""
    rows = to_ragas_rows([_run(), _run(case_id="b", error="boom", reasoning="")])

    assert len(rows) == 1


def test_runs_without_contexts_are_excluded():
    """Context precision over an empty context list is undefined, not zero."""
    rows = to_ragas_rows([_run(contexts=[])])

    assert rows == []


def test_evaluation_of_no_scorable_rows_returns_nulls_not_an_error():
    result = evaluate_runs([_run(contexts=[])], llm=object(), embeddings=object())

    assert result == {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_ragas_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.ragas_metrics'`

- [ ] **Step 3: Write `eval/ragas_metrics.py`**

```python
"""Ragas metrics over completed case runs.

Isolated from ``eval/metrics.py`` so that accuracy and stability scoring stays pure
and offline. Everything here needs a judge model and an embedder, which means a
network call and money.

Both come from the project's existing factories, so this needs no model access the
application does not already have: the reasoning tier and the embedding model are
both verified reachable on the restricted key (spec §3.5).
"""

import logging
from typing import Any

from eval.harness import CaseRun

logger = logging.getLogger(__name__)

METRIC_NAMES = ("context_precision", "context_recall", "faithfulness", "answer_relevancy")


def to_ragas_rows(runs: list[CaseRun]) -> list[dict[str, Any]]:
    """Map completed runs to Ragas' evaluation-sample shape.

    Runs that failed, or that retrieved nothing, are excluded rather than scored as
    zero: context precision over an empty context list is undefined, and a zero
    would be indistinguishable from genuinely bad retrieval.
    """
    return [
        {
            # What the "user" effectively asked: the situation, as the case states it.
            "user_input": _situation(run),
            "response": run.reasoning,
            "retrieved_contexts": list(run.contexts),
            "reference": run.ground_truth,
        }
        for run in runs
        if run.error is None and run.reasoning and run.contexts
    ]


def _situation(run: CaseRun) -> str:
    return f"What is wrong with this plant? Clarifying questions asked: {', '.join(run.questions_asked) or 'none'}."


def evaluate_runs(
    runs: list[CaseRun], *, llm: Any = None, embeddings: Any = None
) -> dict[str, float | None]:
    """Score runs with Ragas, returning ``None`` for any metric that could not run.

    A metric failure is recorded rather than raised: one metric erroring must not
    discard the accuracy numbers from a run that cost real money (spec §5).
    """
    rows = to_ragas_rows(runs)
    if not rows:
        logger.warning("no scorable rows: every run failed or retrieved nothing")
        return dict.fromkeys(METRIC_NAMES)

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        result = evaluate(
            Dataset.from_list(rows),
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
            llm=llm,
            embeddings=embeddings,
        )
        scores = result.to_pandas().mean(numeric_only=True).to_dict()
        return {name: _as_float(scores.get(name)) for name in METRIC_NAMES}
    except Exception as exc:  # noqa: BLE001 — a metric failure is data, not a crash
        logger.warning("ragas evaluation failed: %s", exc)
        return dict.fromkeys(METRIC_NAMES)


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN check
```

> **Implementer note.** Ragas' API surface moves between versions — the metric names above (`user_input`, `response`, `retrieved_contexts`, `reference`) are the current-generation column names. Run `uv run python -c "import ragas; print(ragas.__version__)"` and check the installed version's docs before assuming. If the column names differ, change `to_ragas_rows` and its test together; everything else in this module is version-independent.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/eval/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/ragas_metrics.py tests/unit/eval/test_ragas_metrics.py
git commit -m "feat: add Ragas metrics over completed evaluation runs"
```

---

## Task 14: The report and the CLI

**Files:**
- Create: `eval/report.py`, `eval/run_eval.py`
- Test: `tests/unit/eval/test_report.py`

**Interfaces:**
- Consumes: `AccuracyReport`, `StabilityReport`, `CaseRun`.
- Produces: `render_report(results: dict) -> str`; `build_results(...) -> dict`; a `python -m eval.run_eval` entry point.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for report rendering. Deterministic — no models, no clock."""

from eval.report import render_report

RESULTS = {
    "generated_at": "2026-08-13T10:00:00+00:00",
    "provenance": {
        "reasoning_model": "openai/gpt-4o",
        "vision_model": "scripted",
        "embedding_model": "openai/text-embedding-3-small",
        "temperature": 0.2,
        "corpus_documents": 43,
        "golden_set_size": 28,
    },
    "accuracy": {
        "top1": 0.75,
        "top3": 0.89,
        "scored": 28,
        "failed": 1,
        "by_category": {"watering": {"top1": 1.0, "top3": 1.0, "scored": 4}},
    },
    "ragas": {
        "context_precision": 0.81,
        "context_recall": 0.77,
        "faithfulness": 0.9,
        "answer_relevancy": None,
    },
    "stability": {
        "top1_agreement": 0.6,
        "candidate_churn": 0.42,
        "question_drift": 0.15,
        "cases": 8,
        "runs_per_case": 5.0,
    },
    "near_misses": 3,
}


def test_headline_metrics_appear():
    report = render_report(RESULTS)

    assert "75.0%" in report
    assert "88.9%" in report or "89.0%" in report


def test_provenance_is_recorded():
    """A metrics table without the configuration that produced it is not reproducible."""
    report = render_report(RESULTS)

    assert "openai/gpt-4o" in report
    assert "0.2" in report
    assert "43" in report


def test_a_null_metric_renders_as_not_measured_not_as_zero():
    report = render_report(RESULTS)

    assert "0.0%" not in report.split("Answer relevancy")[1].split("\n")[0]
    assert "not measured" in report.lower()


def test_the_vision_caveat_is_always_present():
    """The golden set injects past vision; the report must say so (spec §3.1)."""
    report = render_report(RESULTS)

    assert "does not measure" in report.lower()
    assert "vision" in report.lower()


def test_failed_cases_are_stated():
    report = render_report(RESULTS)

    assert "1" in report
    assert "failed" in report.lower()


def test_per_category_breakdown_is_rendered():
    report = render_report(RESULTS)

    assert "watering" in report
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/eval/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.report'`

- [ ] **Step 3: Write `eval/report.py`**

```python
"""Render an evaluation results dict as committed markdown."""

from typing import Any

_NOT_MEASURED = "_not measured_"


def _pct(value: Any) -> str:
    if value is None:
        return _NOT_MEASURED
    return f"{float(value) * 100:.1f}%"


def render_report(results: dict) -> str:
    """Render ``eval/REPORT.md`` from a results dict.

    Provenance is rendered first because a metrics table without the configuration
    that produced it cannot be reproduced, and this report is meant to be read
    months later (spec §3.6).
    """
    provenance = results["provenance"]
    accuracy = results["accuracy"]
    ragas = results["ragas"]
    stability = results["stability"]

    lines = [
        "# Evaluation report",
        "",
        f"Generated {results['generated_at']} by `uv run python -m eval.run_eval`.",
        "",
        "## Run provenance",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Reasoning model | `{provenance['reasoning_model']}` |",
        f"| Vision tier | `{provenance['vision_model']}` |",
        f"| Embedding model | `{provenance['embedding_model']}` |",
        f"| Temperature | {provenance['temperature']} |",
        f"| Corpus documents | {provenance['corpus_documents']} |",
        f"| Golden-set size | {provenance['golden_set_size']} |",
        "",
        "## Headline metrics",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Top-1 diagnostic accuracy | {_pct(accuracy['top1'])} |",
        f"| Top-3 diagnostic accuracy | {_pct(accuracy['top3'])} |",
        f"| Context precision | {_pct(ragas['context_precision'])} |",
        f"| Context recall | {_pct(ragas['context_recall'])} |",
        f"| Faithfulness | {_pct(ragas['faithfulness'])} |",
        f"| Answer relevancy | {_pct(ragas['answer_relevancy'])} |",
        "",
        f"{accuracy['scored']} cases scored, of which **{accuracy['failed']} failed** "
        "and are counted in the denominator rather than dropped. "
        f"{results.get('near_misses', 0)} top-1 misses landed on a disorder the case "
        "listed as a confusable neighbour.",
        "",
        "## By category",
        "",
        "| Category | Cases | Top-1 | Top-3 |",
        "|---|---|---|---|",
    ]

    for name, scores in accuracy["by_category"].items():
        lines.append(
            f"| {name} | {scores['scored']} | {_pct(scores['top1'])} | {_pct(scores['top3'])} |"
        )

    lines += [
        "",
        "## Stability",
        "",
        f"{stability['cases']} cases run {stability['runs_per_case']:.0f} times each, on "
        "byte-identical input.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Top-1 agreement | {_pct(stability['top1_agreement'])} |",
        f"| Candidate-set churn | {_pct(stability['candidate_churn'])} |",
        f"| Clarifying-question drift | {_pct(stability['question_drift'])} |",
        "",
        "Churn is mean pairwise Jaccard distance between candidate sets: 0% identical, "
        "100% disjoint. Question drift is the same measure over the clarifying questions "
        "asked, reported separately because those are model-generated — without it, "
        "question variance would read as diagnostic instability.",
        "",
        "## What this does not measure",
        "",
        "**The vision layer.** Golden cases supply symptoms as text and are injected past "
        "`identify_plant` and `assess_symptoms`, so nothing here says anything about "
        "species identification or symptom extraction from a photograph. Every metric "
        "above scores retrieval and reasoning only.",
        "",
        "**Chat.** The chat agent is not exercised, and its token usage is not tracked "
        "at all (`M17`).",
        "",
        "**Real-world photograph quality.** Every case assumes a usable photo; the "
        "quality gate is scripted to pass.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Write `eval/run_eval.py`**

```python
"""Run the golden set and write the results file and report.

Costs real money and takes several minutes. Deliberately a CLI rather than a UI
button: a full run is minutes of model calls, and the report is more valuable as a
reviewable artefact in git than as something that exists only after someone waits
(spec §3.6).

    uv run python -m eval.run_eval
    uv run python -m eval.run_eval --stability-cases 8 --stability-runs 5
"""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent.deps import Deps
from core.config import get_settings
from core.llm import build_embeddings, build_reasoning_model
from core.tracing import configure_tracing
from eval.cases import GoldenCase, load_cases
from eval.harness import CaseRun, run_case
from eval.metrics import accuracy, stability, top1_hit
from eval.ragas_metrics import evaluate_runs
from eval.report import render_report

logger = logging.getLogger(__name__)

GOLDEN_SET = Path("eval/golden_set")
RESULTS_DIR = Path("eval/results")
REPORT_PATH = Path("eval/REPORT.md")


def _near_misses(runs: list[CaseRun], cases: dict[str, GoldenCase]) -> int:
    """Top-1 misses that landed on a disorder the case called confusable."""
    total = 0
    for run in runs:
        if top1_hit(run) or not run.candidates:
            continue
        if run.candidates[0] in set(cases[run.case_id].also_acceptable):
            total += 1
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Plantopia evaluation harness.")
    parser.add_argument("--stability-cases", type=int, default=8)
    parser.add_argument("--stability-runs", type=int, default=5)
    parser.add_argument("--golden-set", type=Path, default=GOLDEN_SET)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    configure_tracing(settings)

    cases = load_cases(args.golden_set)
    logger.info("loaded %d golden cases", len(cases))

    # Build one Deps and one graph per case: the gate and vision tiers are scripted
    # from the case itself (eval/scripted.py), so they cannot be shared.
    runs = [_run_one(case, index) for index, case in enumerate(cases)]

    subset = cases[: args.stability_cases]
    repeats: dict[str, list[CaseRun]] = {
        case.id: [
            _run_one(case, f"stability-{index}-{repeat}")
            for repeat in range(args.stability_runs)
        ]
        for index, case in enumerate(subset)
    }

    accuracy_report = accuracy(runs)
    stability_report = stability(repeats)
    ragas_scores = evaluate_runs(
        runs, llm=_ragas_llm(), embeddings=_ragas_embeddings()
    )

    results = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance": {
            "reasoning_model": settings.reasoning_model,
            "vision_model": "scripted",
            "embedding_model": settings.embedding_model,
            "temperature": settings.default_temperature,
            "corpus_documents": len(list(settings.corpus_path.glob("*.md"))),
            "golden_set_size": len(cases),
        },
        "accuracy": _as_dict(accuracy_report),
        "ragas": ragas_scores,
        "stability": _as_dict(stability_report),
        "near_misses": _near_misses(runs, {case.id: case for case in cases}),
        "cases": [_case_row(run) for run in runs],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = results["generated_at"].replace(":", "-")
    (RESULTS_DIR / f"{stamp}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    logger.info("wrote %s and %s", RESULTS_DIR / f"{stamp}.json", REPORT_PATH)


if __name__ == "__main__":
    main()
```

Add these helpers to the same module, above `main()`:

```python
def _as_dict(report) -> dict:
    from dataclasses import asdict

    return asdict(report)


def _case_row(run: CaseRun) -> dict:
    """Enough to audit one case without storing its full reasoning text."""
    return {
        "case_id": run.case_id,
        "ground_truth": run.ground_truth,
        "category": run.category,
        "candidates": run.candidates,
        "questions_asked": run.questions_asked,
        "error": run.error,
    }


def _ragas_llm():
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(build_reasoning_model())


def _ragas_embeddings():
    from ragas.embeddings import LangchainEmbeddingsWrapper

    return LangchainEmbeddingsWrapper(build_embeddings())


def _run_one(case: GoldenCase, suffix) -> CaseRun:
    """One pass over one case, against a throwaway database.

    A fresh in-memory SQLite per case: `persist` writes a plant, an observation and
    a diagnosis on every run, and thirty cases times five repeats would otherwise
    pour ~180 junk plants into data/plantopia.db. Chroma is built once at module
    import (`_retriever()`) because re-embedding the corpus per case would dominate
    both runtime and cost.
    """
    from datetime import UTC, datetime

    from langgraph.checkpoint.memory import MemorySaver

    from agent.diagnosis_graph import build_diagnosis_graph
    from data.db import apply_schema, connect
    from data.repositories.diagnoses import DiagnosisRepository
    from data.repositories.observations import ObservationRepository
    from data.repositories.plants import PlantRepository
    from data.repositories.roadmap import RoadmapRepository
    from eval.scripted import case_models
    from tools.care_profiles import lookup_plant_care_profile
    from tools.weather import get_local_weather
    from tools.web_search import web_search_plant_info

    settings = get_settings()
    conn = connect(":memory:")
    apply_schema(conn)

    gate, vision = case_models(case)
    deps = Deps(
        settings=settings,
        gate_model=gate,
        vision_model=vision,
        chat_model=build_reasoning_model(),
        retriever=_retriever(),
        plants=PlantRepository(conn),
        observations=ObservationRepository(conn),
        diagnoses=DiagnosisRepository(conn),
        roadmap=RoadmapRepository(conn),
        weather=get_local_weather,
        web_search=lambda query: web_search_plant_info(query, api_key=settings.tavily_api_key),
        care_profile=lookup_plant_care_profile,
        now=lambda: datetime.now(tz=UTC),
    )

    graph = build_diagnosis_graph(deps, MemorySaver())
    try:
        return run_case(case, deps=deps, graph=graph, thread_id=f"eval-{case.id}-{suffix}")
    finally:
        conn.close()


@lru_cache(maxsize=1)
def _retriever():
    """The real corpus retriever, built once for the whole run."""
    from knowledge.ingest import load_corpus
    from knowledge.retriever import ChromaRetriever, build_vectorstore

    settings = get_settings()
    vectorstore = build_vectorstore(
        chunks=load_corpus(settings.corpus_path),
        embeddings=build_embeddings(),
        persist_directory=settings.chroma_path,
    )
    # No image embedder: golden cases carry no photographs, so the cross-modal
    # path has nothing to embed even when multimodal_embeddings is on.
    return ChromaRetriever(vectorstore, None)
```

Add `from functools import lru_cache` to the module imports.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/eval/ -v` then `uv run pytest`
Expected: PASS both.

- [ ] **Step 6: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add eval/report.py eval/run_eval.py tests/unit/eval/test_report.py
git commit -m "feat: add the evaluation report renderer and CLI"
```

---

## Task 15: The Evaluation page, and phase close-out

**Files:**
- Create: `ui/pages/evaluation.py`
- Modify: `app.py:7-12`, `docs/known-limitations.md`, `README.md`
- Test: `tests/ui/test_evaluation_page.py`

**Interfaces:**
- Consumes: the results JSON shape from Task 14.
- Produces: a navigable Evaluation page.

- [ ] **Step 1: Write the failing tests**

```python
"""UI tests for the Evaluation page."""

import json

import pytest

pytestmark = pytest.mark.ui


def _write_results(directory, payload) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2026-08-13T10-00-00+00-00.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_the_empty_state_names_the_command(tmp_path, monkeypatch):
    """No traceback when nothing has been run yet (spec §5)."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(tmp_path / "missing"))
    app = AppTest.from_file("ui/pages/evaluation.py").run()

    assert not app.exception
    assert any("eval.run_eval" in info.value for info in app.info)


def test_headline_metrics_render(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    results_dir = tmp_path / "results"
    _write_results(results_dir, _payload())
    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(results_dir))

    app = AppTest.from_file("ui/pages/evaluation.py").run()

    assert not app.exception
    assert any("75" in str(metric.value) for metric in app.metric)


def test_the_vision_caveat_is_shown(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    results_dir = tmp_path / "results"
    _write_results(results_dir, _payload())
    monkeypatch.setenv("PLANTOPIA_EVAL_RESULTS_DIR", str(results_dir))

    app = AppTest.from_file("ui/pages/evaluation.py").run()

    body = " ".join(m.value for m in app.markdown)
    assert "vision" in body.lower()
```

Define `_payload()` in the test module returning the same dict shape as `RESULTS` in `tests/unit/eval/test_report.py` (repeat it — the engineer may read these out of order).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/ui/test_evaluation_page.py -m ui -v`
Expected: FAIL — the page does not exist.

- [ ] **Step 3: Write the page**

```python
"""Evaluation results, rendered from the newest committed results file.

Renders only — it never runs the harness. A full evaluation is minutes of model
calls and real money, so it lives behind `uv run python -m eval.run_eval`, and this
page reads what that wrote (spec §4).
"""

import json
import os
from pathlib import Path

import streamlit as st

st.title("📊 Evaluation")


def _results_dir() -> Path:
    return Path(os.environ.get("PLANTOPIA_EVAL_RESULTS_DIR", "eval/results"))


def _latest_results() -> dict | None:
    files = sorted(_results_dir().glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


results = _latest_results()

if results is None:
    st.info(
        "No evaluation has been run yet. Run `uv run python -m eval.run_eval` to "
        "generate a report — it takes several minutes and makes real model calls."
    )
    st.stop()

provenance = results["provenance"]
st.caption(
    f"Generated {results['generated_at']} · reasoning model "
    f"`{provenance['reasoning_model']}` · temperature {provenance['temperature']} · "
    f"{provenance['corpus_documents']} corpus documents · "
    f"{provenance['golden_set_size']} golden cases"
)

accuracy = results["accuracy"]
ragas = results["ragas"]


def _pct(value) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


left, middle, right = st.columns(3)
left.metric("Top-1 accuracy", _pct(accuracy["top1"]))
middle.metric("Top-3 accuracy", _pct(accuracy["top3"]))
right.metric("Faithfulness", _pct(ragas["faithfulness"]))

st.subheader("Retrieval quality")
st.dataframe(
    {
        "Metric": ["Context precision", "Context recall", "Answer relevancy"],
        "Score": [
            _pct(ragas["context_precision"]),
            _pct(ragas["context_recall"]),
            _pct(ragas["answer_relevancy"]),
        ],
    },
    hide_index=True,
)

st.subheader("By category")
by_category = accuracy["by_category"]
st.bar_chart({name: scores["top1"] for name, scores in by_category.items()})

st.subheader("Stability")
stability = results["stability"]
st.caption(
    f"{stability['cases']} cases run {stability['runs_per_case']:.0f} times each on "
    "byte-identical input."
)
first, second, third = st.columns(3)
first.metric("Top-1 agreement", _pct(stability["top1_agreement"]))
second.metric("Candidate churn", _pct(stability["candidate_churn"]))
third.metric("Question drift", _pct(stability["question_drift"]))

st.subheader("What this does not measure")
st.markdown(
    "- **The vision layer.** Golden cases supply symptoms as text and are injected "
    "past `identify_plant` and `assess_symptoms`, so nothing here scores species "
    "identification or symptom extraction from a photograph.\n"
    "- **Chat.** Not exercised, and its token usage is not tracked at all (`M17`).\n"
    "- **Photograph quality.** Every case assumes a usable photo; the quality gate "
    "is scripted to pass."
)
```

- [ ] **Step 4: Register the page**

In `app.py`, add to the `pages` list after Chat:

```python
    st.Page("ui/pages/evaluation.py", title="Evaluation", icon="📊"),
```

- [ ] **Step 5: Generate the first real report**

```bash
uv run python -m eval.run_eval
```

This costs money and takes minutes. Read `eval/REPORT.md` afterwards and sanity-check it: are the accuracy numbers plausible, did more than one or two cases fail, did any category score 0%? A 0% category usually means a bad `ground_truth` slug rather than a bad agent — cross-check against `knowledge/corpus/`.

- [ ] **Step 6: Close out the phase docs**

In `docs/known-limitations.md`, add a short section under "First live run" recording what the harness actually measured about the stability finding — replacing the open question at `known-limitations.md:91` with a number. Reference `eval/REPORT.md` rather than duplicating the table.

In `README.md`, document the Evaluation page and the `uv run python -m eval.run_eval` command, and note that `ragas`/`pyyaml` are dev-only dependencies.

- [ ] **Step 7: Run everything**

Run: `uv run pytest && uv run pytest -m ui`
Expected: PASS both, coverage above 85%.

- [ ] **Step 8: Commit**

```bash
uv run ruff check . && uv run ruff format .
git add ui/pages/evaluation.py app.py eval/REPORT.md eval/results/ docs/ README.md tests/ui/
git commit -m "feat: add the Evaluation page and the first evaluation report"
```

---

## Done when

- `uv run pytest` passes with coverage above 85%, and `uv run pytest -m ui` passes.
- A real diagnosis writes non-null `token_usage_json` and `cost_usd`, and the badge renders on both the result view and the timeline.
- `PLANTOPIA_LANGSMITH_API_KEY` set produces traces; unset changes nothing.
- `uv run python -m eval.run_eval` produces `eval/results/*.json` and `eval/REPORT.md`, and the Evaluation page renders them.
- `M12` is struck through in `docs/known-limitations.md` and `M17` (chat cost) is recorded.
