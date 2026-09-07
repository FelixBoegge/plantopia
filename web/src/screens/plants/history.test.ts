import { describe, expect, it } from "vitest";

import type { Diagnosis, Message, Observation, RoadmapStep } from "@/api/types";
import {
  escalationsIn,
  ESCALATION_TOOL,
  observedAt,
  seriesOf,
  steppedAt,
  timelineOf,
} from "@/screens/plants/history";

function observation(overrides: Partial<Observation> = {}): Observation {
  return {
    id: "obs-1",
    plant_id: "plant-1",
    kind: "initial",
    photo_refs: ["photo-1"],
    user_notes: null,
    created_at: "2026-08-20T09:00:00Z",
    captured_at: null,
    latitude: null,
    longitude: null,
    weather: null,
    ...overrides,
  };
}

function diagnosis(overrides: Partial<Diagnosis> = {}): Diagnosis {
  return {
    id: "diag-1",
    plant_id: "plant-1",
    observation_id: "obs-1",
    is_healthy: false,
    reasoning: "Yellowing consistent with overwatering.",
    candidates: [],
    species_method: null,
    progress_verdict: null,
    species_confirmed: false,
    weather: null,
    created_at: "2026-08-20T09:05:00Z",
    cost_usd: null,
    token_usage: null,
    sources: [],
    ...overrides,
  };
}

function step(overrides: Partial<RoadmapStep> = {}): RoadmapStep {
  return {
    id: "step-1",
    diagnosis_id: "diag-1",
    ordinal: 1,
    action: "Let the top third dry out",
    rationale: "Reduces root saturation",
    success_signal: "New growth firms up",
    tier: 1,
    due_date: "2026-08-25T00:00:00Z",
    status: "pending",
    completed_at: null,
    ...overrides,
  };
}

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    plant_id: "plant-1",
    role: "assistant",
    content: "I have flagged this for a fresh look.",
    tool_calls: null,
    created_at: "2026-08-22T10:00:00Z",
    ...overrides,
  };
}

const WEATHER = {
  min_temp_c: -1,
  max_temp_c: 20,
  total_precip_mm: 4,
  frost_days: 1,
  heat_days: 0,
  days_covered: 2,
  days: [
    { on: "2026-08-18", min_temp_c: -1, max_temp_c: 18, precip_mm: 0 },
    { on: "2026-08-19", min_temp_c: 8, max_temp_c: 20, precip_mm: 4 },
  ],
  forecast: [],
};

describe("when an observation happened", () => {
  it("uses the capture date where there is one", () => {
    const seen = observedAt(
      observation({ captured_at: "2026-08-10T10:50:00Z", created_at: "2026-08-20T09:00:00Z" }),
    );

    expect(seen).toEqual({ at: "2026-08-10T10:50:00Z", dated: "captured" });
  });

  it("falls back to the upload, and says that is what it did", () => {
    // A history ordered by upload puts events in an order the plant never experienced — but
    // an upload date is what there is, and claiming it is a capture date would be worse.
    const seen = observedAt(observation({ captured_at: null }));

    expect(seen).toEqual({ at: "2026-08-20T09:00:00Z", dated: "uploaded" });
  });
});

describe("when a roadmap step belongs", () => {
  it("sits at its completion once it is done", () => {
    expect(steppedAt(step({ status: "done", completed_at: "2026-08-26T08:00:00Z" }))).toEqual({
      at: "2026-08-26T08:00:00Z",
      settled: true,
    });
  });

  it("sits at its completion when it was skipped", () => {
    // Skipping is a decision somebody made at a moment, which is history.
    expect(steppedAt(step({ status: "skipped", completed_at: "2026-08-26T08:00:00Z" }))).toEqual({
      at: "2026-08-26T08:00:00Z",
      settled: true,
    });
  });

  it("is nowhere while it is still pending", () => {
    // <Roadmap> already lists every pending step with its due date and a checkbox. Showing
    // the same item twice, where only one of them can be acted on, is worse than once.
    expect(steppedAt(step({ status: "pending", completed_at: null }))).toBeNull();
  });
});

describe("escalations in a transcript", () => {
  it("finds one, with its reason", () => {
    const found = escalationsIn([
      message({
        tool_calls: [
          {
            name: ESCALATION_TOOL,
            args: { reason: "New black spots described that the last diagnosis did not cover" },
            result: "flagged",
          },
        ],
      }),
    ]);

    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({
      kind: "escalation",
      at: "2026-08-22T10:00:00Z",
      reason: "New black spots described that the last diagnosis did not cover",
    });
  });

  it("ignores an ordinary exchange", () => {
    const found = escalationsIn([
      message({ tool_calls: [{ name: "search_plant_knowledge", args: {}, result: "…" }] }),
      message({ id: "msg-2", tool_calls: null }),
      message({ id: "msg-3", role: "user", content: "Why are the leaves yellow?" }),
    ]);

    expect(found).toEqual([]);
  });

  it("survives a call with no reason recorded", () => {
    const found = escalationsIn([
      message({ tool_calls: [{ name: ESCALATION_TOOL, args: {}, result: "" }] }),
    ]);

    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({ reason: "" });
  });

  it("keeps two calls in one turn distinct", () => {
    const found = escalationsIn([
      message({
        tool_calls: [
          { name: ESCALATION_TOOL, args: { reason: "first" }, result: "" },
          { name: ESCALATION_TOOL, args: { reason: "second" }, result: "" },
        ],
      }),
    ]);

    expect(new Set(found.map((event) => event.id)).size).toBe(2);
  });
});

describe("the weather worth drawing", () => {
  it("is the series where there is one", () => {
    expect(seriesOf(observation({ weather: WEATHER }))).toBe(WEATHER);
  });

  it("is nothing where there is none", () => {
    expect(seriesOf(observation({ weather: null }))).toBeNull();
  });

  it("is nothing for a summary stored before the series was kept", () => {
    // It still carries aggregates, which a chart cannot show and a table would show as an
    // empty one.
    expect(seriesOf(observation({ weather: { ...WEATHER, days: [] } }))).toBeNull();
  });
});

describe("the merged timeline", () => {
  it("puts four differently-ordered sources into one order", () => {
    const events = timelineOf({
      observations: [
        observation({ id: "obs-old", captured_at: "2026-08-01T00:00:00Z" }),
        observation({ id: "obs-new", captured_at: "2026-08-20T00:00:00Z" }),
      ],
      diagnoses: [diagnosis({ id: "diag-new", created_at: "2026-08-20T01:00:00Z" })],
      steps: [step({ id: "step-done", completed_at: "2026-08-21T00:00:00Z", status: "done" })],
      messages: [
        message({
          id: "msg-esc",
          created_at: "2026-08-22T00:00:00Z",
          tool_calls: [{ name: ESCALATION_TOOL, args: { reason: "worse" }, result: "" }],
        }),
      ],
    });

    expect(events.map((event) => event.id)).toEqual([
      "msg-esc:0",
      "step-done",
      "diag-new",
      "obs-new",
      "obs-old",
    ]);
  });

  it("orders by capture rather than upload", () => {
    // The photograph taken first comes first, even though it was uploaded last.
    const events = timelineOf({
      observations: [
        observation({
          id: "uploaded-first",
          captured_at: "2026-08-20T00:00:00Z",
          created_at: "2026-08-20T00:00:00Z",
        }),
        observation({
          id: "taken-first",
          captured_at: "2026-08-01T00:00:00Z",
          created_at: "2026-08-25T00:00:00Z",
        }),
      ],
      diagnoses: [],
      steps: [],
    });

    expect(events.map((event) => event.id)).toEqual(["uploaded-first", "taken-first"]);
  });

  it("renders without a transcript, and gains escalations when one arrives", () => {
    const sources = {
      observations: [observation()],
      diagnoses: [diagnosis()],
      steps: [],
    };

    const without = timelineOf(sources);
    const withOne = timelineOf({
      ...sources,
      messages: [
        message({ tool_calls: [{ name: ESCALATION_TOOL, args: { reason: "worse" }, result: "" }] }),
      ],
    });

    expect(without.some((event) => event.kind === "escalation")).toBe(false);
    expect(withOne.some((event) => event.kind === "escalation")).toBe(true);
    expect(withOne).toHaveLength(without.length + 1);
  });

  it("keeps an observation that knows nothing about itself", () => {
    const events = timelineOf({
      observations: [
        observation({ id: "bare", captured_at: null, latitude: null, weather: null }),
      ],
      diagnoses: [],
      steps: [],
    });

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ id: "bare", dated: "uploaded" });
  });

  it("leaves a pending step out entirely", () => {
    // Found by implementation: the step action appeared twice on the plant page, once here
    // and once in <Roadmap>. The plan is the actionable surface; this one is history.
    const events = timelineOf({
      observations: [],
      diagnoses: [],
      steps: [
        step({ id: "pending", status: "pending", completed_at: null }),
        step({ id: "done", status: "done", completed_at: "2026-08-26T00:00:00Z" }),
      ],
    });

    expect(events.map((event) => event.id)).toEqual(["done"]);
  });

  it("is empty for a plant with no history", () => {
    expect(timelineOf({ observations: [], diagnoses: [], steps: [] })).toEqual([]);
  });

  it("breaks ties stably", () => {
    // A diagnosis and the observation it was made from can share an instant on a fast run.
    const at = "2026-08-20T00:00:00Z";
    const once = timelineOf({
      observations: [observation({ id: "aaa", captured_at: at })],
      diagnoses: [diagnosis({ id: "zzz", created_at: at })],
      steps: [],
    });
    const twice = timelineOf({
      diagnoses: [diagnosis({ id: "zzz", created_at: at })],
      observations: [observation({ id: "aaa", captured_at: at })],
      steps: [],
    });

    expect(once.map((event) => event.id)).toEqual(twice.map((event) => event.id));
  });
});

describe("a diagnosis and the photographs it read", () => {
  /**
   * They are one event in a plant's life and used to be two in this list, because they are
   * dated by different clocks: an observation by when the photograph was taken, a diagnosis
   * by when it ran. Diagnosing an August photograph today put the two at opposite ends of
   * the history, with a second run's photographs in between.
   */
  it("bundles a diagnosis into the observation it read", () => {
    const events = timelineOf({
      observations: [observation({ id: "obs-1", captured_at: "2026-08-14T09:00:00Z" })],
      diagnoses: [
        diagnosis({
          id: "diag-1",
          observation_id: "obs-1",
          created_at: "2026-09-03T09:00:00Z",
        }),
      ],
      steps: [],
    });

    expect(events).toHaveLength(1);
    const [only] = events;
    expect(only?.kind).toBe("observation");
    expect(only?.kind === "observation" && only.diagnosis?.id).toBe("diag-1");
  });

  it("orders the bundles by when each diagnosis ran", () => {
    // The deciding case, and the reason this is not ordered by capture date: the September
    // photographs are diagnosed first and the August ones second. Ordered by capture, the
    // second run would appear *below* the first — the list rearranging itself behind you.
    const events = timelineOf({
      observations: [
        observation({ id: "obs-old", captured_at: "2026-08-14T09:00:00Z" }),
        observation({ id: "obs-new", captured_at: "2026-09-02T09:00:00Z" }),
      ],
      diagnoses: [
        diagnosis({ id: "d-new", observation_id: "obs-new", created_at: "2026-09-03T09:00:00Z" }),
        diagnosis({ id: "d-old", observation_id: "obs-old", created_at: "2026-09-03T10:00:00Z" }),
      ],
      steps: [],
    });

    expect(events.map((event) => event.id)).toEqual(["obs-old", "obs-new"]);
  });

  it("keeps the capture date beside the run date", () => {
    // Both are shown: they differ whenever an old photograph is diagnosed today, which is
    // the case that made this confusing in the first place.
    const [entry] = timelineOf({
      observations: [observation({ id: "obs-1", captured_at: "2026-08-14T09:00:00Z" })],
      diagnoses: [
        diagnosis({ observation_id: "obs-1", created_at: "2026-09-03T09:00:00Z" }),
      ],
      steps: [],
    });

    expect(entry?.at).toBe("2026-09-03T09:00:00Z");
    expect(entry?.kind === "observation" && entry.photographedAt).toBe(
      "2026-08-14T09:00:00Z",
    );
  });

  it("keeps an observation that has no diagnosis yet", () => {
    const events = timelineOf({
      observations: [observation({ id: "obs-1" })],
      diagnoses: [],
      steps: [],
    });

    const [only] = events;
    expect(only?.kind === "observation" && only.diagnosis).toBeNull();
  });

  it("keeps a diagnosis whose observation is not here", () => {
    // Nothing may disappear from a history because two records failed to find each other.
    const events = timelineOf({
      observations: [],
      diagnoses: [diagnosis({ id: "orphan", observation_id: "obs-missing" })],
      steps: [],
    });

    expect(events.map((event) => event.kind)).toEqual(["diagnosis"]);
  });
});
