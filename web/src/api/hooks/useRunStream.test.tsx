/**
 * Watching a run, including the parts that only happen when something goes wrong.
 *
 * The stream is fabricated rather than served, because what is worth proving is a dropped
 * connection and a duplicated event across a reconnect — neither of which a working server
 * produces on request.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { useRunStream } from "@/api/hooks/useRunStream";
import { forget, setToken } from "@/api/session";
import { server } from "@/test/server";

const RUN = "01a0-run";

function frames(...text: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of text) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

function step(sequence: number, id: string, description: string): string {
  return `id: ${sequence}\nevent: step\ndata: {"step":"${id}","description":"${description}"}\n\n`;
}

function completed(sequence: number, extra = ""): string {
  return `id: ${sequence}\nevent: completed\ndata: {"diagnosis_id":"01a0-diagnosis","plant_id":"01a0-plant","rejected":false,"reason":null${extra}}\n\n`;
}

function serve(
  body: () => ReadableStream<Uint8Array>,
  onRequest?: (r: Request) => void,
) {
  server.use(
    http.get(`/api/v1/runs/${RUN}/events`, ({ request }) => {
      onRequest?.(request);
      return new HttpResponse(body(), {
        headers: { "Content-Type": "text/event-stream" },
      });
    }),
  );
}

afterEach(forget);

describe("watching a run", () => {
  it("shows each step as it arrives", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        step(2, "identifying", "Identifying the species"),
        completed(3),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(result.current.steps.map((s) => s.description)).toEqual([
      "Checking the photographs",
      "Identifying the species",
    ]);
  });

  it("carries what a step called and how long it took", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        `id: 1
event: step
data: {"step":"identifying","description":"Identifying the species","calls":"acme/see-1 via OpenRouter","duration_ms":4120}

`,
        completed(2),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    const [carried] = result.current.steps;
    expect(carried?.calls).toBe("acme/see-1 via OpenRouter");
    expect(carried?.duration_ms).toBe(4120);
  });

  it("keeps a step that carries neither", async () => {
    // Replayed history from a run that started before either was recorded.
    setToken("fresh");
    serve(() =>
      frames(step(1, "identifying", "Identifying the species"), completed(2)),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    const [bare] = result.current.steps;
    expect(bare).toBeDefined();
    expect(bare?.calls).toBeUndefined();
    expect(bare?.duration_ms).toBeUndefined();
  });

  it("sends the token as a header", async () => {
    setToken("fresh");
    let authorised: string | null = null;
    serve(
      () => frames(completed(1)),
      (request) => {
        authorised = request.headers.get("Authorization");
      },
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(authorised).toBe("Bearer fresh");
  });

  it("puts nothing in the URL", async () => {
    setToken("fresh");
    let url = "";
    serve(
      () => frames(completed(1)),
      (request) => {
        url = request.url;
      },
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(url).not.toContain("fresh");
  });

  it("reports the questions when the run pauses", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often do you water it?","kind":"text","options":[]}]}\n\n',
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.questions).not.toBeNull());
    expect(result.current.questions?.[0]?.key).toBe("watering");
  });

  it("is paused once the questions arrive", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often?","kind":"text","options":[]}]}\n\n',
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.questions).not.toBeNull());
    expect(result.current.paused).toBe(true);
  });

  it("is no longer paused once a step arrives after the questions", async () => {
    // Nothing publishes a step from inside the interrupt, so a step seen once paused can
    // only mean the resumed pass has started — on the very same connection that saw the
    // questions arrive, exactly as a run answered without navigating away ever produces.
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often?","kind":"text","options":[]}]}\n\n',
        step(3, "diagnosing", "Weighing the evidence"),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.steps).toHaveLength(2));
    expect(result.current.paused).toBe(false);
    // Still there, locked — only the pause has lifted.
    expect(result.current.questions).not.toBeNull();
  });

  it("reads a run already past its pause the same way on a fresh connection", async () => {
    // The exact shape a reconnect replays: the questions event and everything that
    // happened after it, delivered together rather than watched live one at a time. This
    // is what a run resumed by navigating away and back looks like — a brand new
    // connection and a mutation that never ran, neither of which was involved when the
    // answers were actually sent.
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often?","kind":"text","options":[]}]}\n\n',
        step(3, "diagnosing", "Weighing the evidence"),
        step(4, "building the plan", "Building the plan"),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.steps).toHaveLength(3));
    expect(result.current.paused).toBe(false);
  });

  it("keeps the steps already shown when the questions arrive", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often?","kind":"text","options":[]}]}\n\n',
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.questions).not.toBeNull());
    expect(result.current.steps).toHaveLength(1);
  });

  it("reports what a completed run produced", async () => {
    setToken("fresh");
    serve(() => frames(completed(1)));

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending?.kind).toBe("completed"));
    expect(result.current.ending?.diagnosisId).toBe("01a0-diagnosis");
    expect(result.current.ending?.plantId).toBe("01a0-plant");
  });

  it("reports a failure as an ending rather than a silence", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        'id: 1\nevent: failed\ndata: {"detail":"The run could not be completed."}\n\n',
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending?.kind).toBe("failed"));
    expect(result.current.ending?.detail).toBe(
      "The run could not be completed.",
    );
  });

  it("reports a cancellation", async () => {
    setToken("fresh");
    serve(() => frames("id: 1\nevent: cancelled\ndata: {}\n\n"));

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending?.kind).toBe("cancelled"));
  });

  it("reports a run that produced nothing, and why", async () => {
    setToken("fresh");
    serve(() =>
      frames(
        'id: 1\nevent: completed\ndata: {"diagnosis_id":null,"plant_id":null,"rejected":true,"reason":"This looks like a doorknob, not a plant."}\n\n',
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(result.current.ending?.rejected).toBe(true);
    expect(result.current.ending?.reason).toContain("doorknob");
  });

  it("ignores keep-alive traffic", async () => {
    setToken("fresh");
    serve(() => frames(": ping - 2026-01-01\n\n", completed(1)));

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(result.current.steps).toHaveLength(0);
  });
});

describe("when the connection drops", () => {
  it("reconnects and continues from the last event seen", async () => {
    setToken("fresh");
    let attempt = 0;
    const asked: (string | null)[] = [];
    server.use(
      http.get(`/api/v1/runs/${RUN}/events`, ({ request }) => {
        asked.push(request.headers.get("Last-Event-ID"));
        attempt += 1;
        const body =
          attempt === 1
            ? frames(step(1, "checking", "Checking the photographs")) // then ends, mid-run
            : frames(
                step(2, "identifying", "Identifying the species"),
                completed(3),
              );
        return new HttpResponse(body, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull(), {
      timeout: 5000,
    });
    expect(asked).toEqual([null, "1"]);
    expect(result.current.steps.map((s) => s.description)).toEqual([
      "Checking the photographs",
      "Identifying the species",
    ]);
  });

  it("renders an event repeated across the reconnect exactly once", async () => {
    // The server subscribes before it replays, so the tail of a replay can arrive twice.
    // Rendering the duplicate would show a step twice on precisely the reconnect that is
    // meant to be invisible.
    setToken("fresh");
    let attempt = 0;
    server.use(
      http.get(`/api/v1/runs/${RUN}/events`, () => {
        attempt += 1;
        const body =
          attempt === 1
            ? frames(step(1, "checking", "Checking the photographs"))
            : frames(
                step(1, "checking", "Checking the photographs"),
                completed(2),
              );
        return new HttpResponse(body, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull(), {
      timeout: 5000,
    });
    expect(result.current.steps).toHaveLength(1);
  });

  it("does not reconnect to a run that has already ended", async () => {
    // There is nothing to come back for, and a stream reopened every second on a finished
    // run is a request per second for ever.
    setToken("fresh");
    let attempts = 0;
    server.use(
      http.get(`/api/v1/runs/${RUN}/events`, () => {
        attempts += 1;
        return new HttpResponse(frames(completed(1)), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { result } = renderHook(() => useRunStream(RUN));
    await waitFor(() => expect(result.current.ending).not.toBeNull());
    await new Promise((resolve) => setTimeout(resolve, RECONNECT_WAIT));

    expect(attempts).toBe(1);
  });

  it("retries a stream that could not be opened", async () => {
    setToken("fresh");
    let attempt = 0;
    server.use(
      http.get(`/api/v1/runs/${RUN}/events`, () => {
        attempt += 1;
        return attempt === 1
          ? new HttpResponse(null, { status: 502 })
          : new HttpResponse(frames(completed(1)), {
              headers: { "Content-Type": "text/event-stream" },
            });
      }),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull(), {
      timeout: 5000,
    });
    expect(attempt).toBe(2);
  });

  it("stops when the component goes away", async () => {
    setToken("fresh");
    let attempts = 0;
    server.use(
      http.get(`/api/v1/runs/${RUN}/events`, () => {
        attempts += 1;
        return new HttpResponse(frames(step(1, "checking", "Checking")), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    const { unmount, result } = renderHook(() => useRunStream(RUN));
    await waitFor(() => expect(result.current.steps).toHaveLength(1));
    unmount();
    const seen = attempts;
    await new Promise((resolve) => setTimeout(resolve, RECONNECT_WAIT));

    expect(attempts).toBe(seen);
  });
});

// Long enough for a reconnect to have happened if one were going to.
const RECONNECT_WAIT = 1500;

describe("watching nothing", () => {
  it("does not open a stream without a run", () => {
    const { result } = renderHook(() => useRunStream(null));

    expect(result.current.steps).toEqual([]);
    expect(result.current.connected).toBe(false);
  });
});

describe("steps that share a sentence", () => {
  it("shows a repeated step once rather than twice in a row", async () => {
    // `guard_input` and `quality_check` are both "Checking the photographs" by design. Two
    // nodes, two events, one thing a person is being told.
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        step(2, "checking", "Checking the photographs"),
        step(3, "identifying", "Identifying the species"),
        completed(4),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(result.current.steps.map((s) => s.description)).toEqual([
      "Checking the photographs",
      "Identifying the species",
    ]);
  });

  it("still shows a step that comes back later in the run", async () => {
    // Consecutive is the rule, not "ever seen". A run that checks, diagnoses and checks
    // again has done the second check.
    setToken("fresh");
    serve(() =>
      frames(
        step(1, "checking", "Checking the photographs"),
        step(2, "diagnosing", "Weighing the evidence"),
        step(3, "checking", "Checking the photographs"),
        completed(4),
      ),
    );

    const { result } = renderHook(() => useRunStream(RUN));

    await waitFor(() => expect(result.current.ending).not.toBeNull());
    expect(result.current.steps).toHaveLength(3);
  });
});
