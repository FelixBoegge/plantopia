import { useEffect, useRef, useState } from "react";

import { readEvents } from "@/api/events";
import { currentToken } from "@/api/session";
import type { Question, RunStatus, SpeciesCandidate } from "@/api/types";

/**
 * Watching one run.
 *
 * **`fetch` and a `ReadableStream`, not `EventSource`.** `EventSource` cannot set an
 * `Authorization` header, and every workaround puts the access token in the query string —
 * where it lands in the server's access log and the browser's history, for a credential
 * deliberately never written to storage.
 *
 * **Reconnecting loses nothing.** The last event's id goes back as `Last-Event-ID` and the
 * server replays from there. Because it subscribes before it replays, the first live events
 * may repeat the tail of the replay — so the sequence decides, here, once, rather than in
 * each component that renders a step.
 *
 * The stream is the only source of progress. What a run finally produced is read from the
 * run itself: an event is a notification, and a client that reconstructed the result from
 * notifications would be a second implementation of what a run is.
 */

export interface Step {
  sequence: number;
  id: string;
  description: string;
}

export interface Watched {
  steps: Step[];
  questions: Question[] | null;
  /**
   * The identifications to choose between, when there is a choice.
   *
   * `null` covers two different situations that want the same treatment: the run has not
   * paused yet, and the run paused with every method naming the same plant. Neither is a
   * question to put to anybody.
   */
  identification: SpeciesCandidate[] | null;
  /** Set when the run ends, whatever the ending. */
  ending: {
    kind: "completed" | "failed" | "cancelled";
    diagnosisId: string | null;
    plantId: string | null;
    rejected: boolean;
    reason: string | null;
    detail: string | null;
  } | null;
  connected: boolean;
}

const NOTHING: Watched = {
  steps: [],
  questions: null,
  identification: null,
  ending: null,
  connected: false,
};

// How long to wait before reconnecting a stream that ended without saying why. Short: the
// run is still working and somebody is watching a blank panel until this elapses.
const RECONNECT_MS = 750;

export function useRunStream(runId: string | null): Watched {
  const [watched, setWatched] = useState<Watched>(NOTHING);

  // Outside state on purpose: a re-render must not lose track of where the stream was, and
  // updating them must not cause one.
  const highest = useRef(0);
  const finished = useRef(false);

  useEffect(() => {
    if (!runId) return;

    highest.current = 0;
    finished.current = false;
    setWatched(NOTHING);

    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function follow(): Promise<void> {
      try {
        const response = await fetch(`/api/v1/runs/${runId}/events`, {
          signal: abort.signal,
          headers: {
            Authorization: `Bearer ${currentToken() ?? ""}`,
            // Empty on the first attempt, which the server reads as "from the beginning".
            ...(highest.current
              ? { "Last-Event-ID": String(highest.current) }
              : {}),
          },
        });

        if (!response.ok || !response.body) {
          schedule();
          return;
        }

        setWatched((seen) => ({ ...seen, connected: true }));

        for await (const event of readEvents(response.body)) {
          const sequence = Number(event.id ?? 0);
          // Already seen. Subscribing before replaying is what makes this possible, and
          // rendering the duplicate would show a step twice on exactly the reconnect that
          // is supposed to be invisible.
          if (sequence <= highest.current) continue;
          highest.current = sequence;
          apply(sequence, event.event, event.data);
        }
      } catch {
        // Aborted, or the connection dropped. Both are handled the same way.
      }

      setWatched((seen) => ({ ...seen, connected: false }));
      schedule();
    }

    function schedule(): void {
      // A finished run has said so, and there is nothing to come back for.
      if (finished.current || abort.signal.aborted) return;
      timer = setTimeout(() => void follow(), RECONNECT_MS);
    }

    function apply(sequence: number, kind: string, data: unknown): void {
      const payload = (data ?? {}) as Record<string, unknown>;

      if (kind === "step") {
        setWatched((seen) => {
          const id = String(payload.step ?? "");
          // Several graph nodes deliberately share one sentence — `guard_input` and
          // `quality_check` are both "Checking the photographs", because the distinction is
          // internal and the sentence is what somebody reads. Two nodes then produce two
          // events, and rendering both shows the same line twice in a row, which reads as
          // something having happened twice.
          //
          // Consecutive only: a step that genuinely recurs later in a run is a different
          // thing from a node boundary, and is still worth showing.
          if (seen.steps.at(-1)?.id === id) return seen;

          return {
            ...seen,
            steps: [
              ...seen.steps,
              {
                sequence,
                id,
                description: String(payload.description ?? ""),
              },
            ],
          };
        });
        return;
      }

      if (kind === "questions") {
        setWatched((seen) => ({
          ...seen,
          questions: (payload.questions as Question[]) ?? [],
          // Absent when the methods agreed, which is why this reads the key rather than
          // the length: an empty array and no array mean the same thing here, and only one
          // of them is ever sent.
          identification:
            (payload.identification as SpeciesCandidate[] | undefined) ?? null,
        }));
        return;
      }

      if (kind === "completed" || kind === "failed" || kind === "cancelled") {
        finished.current = true;
        setWatched((seen) => ({
          ...seen,
          questions: null,
          ending: {
            kind,
            diagnosisId: (payload.diagnosis_id as string | null) ?? null,
            plantId: (payload.plant_id as string | null) ?? null,
            rejected: payload.rejected === true,
            reason: (payload.reason as string | null) ?? null,
            detail: (payload.detail as string | null) ?? null,
          },
        }));
      }
    }

    void follow();

    return () => {
      abort.abort();
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  return watched;
}

/** Whether a status means the run is over. Used to decide whether to watch at all. */
export function hasFinished(status: RunStatus | undefined): boolean {
  return (
    status === "completed" || status === "failed" || status === "cancelled"
  );
}
