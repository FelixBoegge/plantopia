import type {
  Diagnosis,
  Message,
  Observation,
  RoadmapStep,
  WeatherSummary,
} from "@/api/types";

/**
 * A plant's history as one sequence.
 *
 * Four sources, each ordered differently by the repository that serves it — observations
 * oldest first, diagnoses newest first, roadmap steps by their diagnosis's date and then by
 * ordinal — and none of those orders is the one a history reads in. So this merges and
 * re-sorts rather than concatenating.
 *
 * A pure function over data the plant page already has, tested without a browser. The
 * rendering decides what an event *looks* like; this decides what happened and when.
 */

/** The tool the chat agent calls when it judges a fresh diagnosis is warranted. */
export const ESCALATION_TOOL = "suggest_new_diagnosis";

export type TimelineEvent =
  | {
      kind: "observation";
      id: string;
      at: string;
      /** Whether the date above is when the photograph was taken or only when it arrived. */
      dated: "captured" | "uploaded";
      observation: Observation;
    }
  | { kind: "diagnosis"; id: string; at: string; diagnosis: Diagnosis }
  | { kind: "step"; id: string; at: string; step: RoadmapStep }
  | { kind: "escalation"; id: string; at: string; reason: string };

/**
 * When an observation happened.
 *
 * The capture date where there is one, the upload otherwise. The two differ for anybody who
 * did not upload immediately, and a history ordered by upload puts events in an order the
 * plant never experienced — the same defect the weather window had before capture dates were
 * read. `dated` carries which of the two this is, so nothing downstream has to claim a
 * capture date the photograph never declared.
 */
export function observedAt(observation: Observation): {
  at: string;
  dated: "captured" | "uploaded";
} {
  return observation.captured_at
    ? { at: observation.captured_at, dated: "captured" }
    : { at: observation.created_at, dated: "uploaded" };
}

/**
 * When a roadmap step happened, or `null` if it has not.
 *
 * Only a settled step — done or skipped — is history. A pending step has not happened at
 * all, and putting it here would duplicate the plan: `<Roadmap>` already lists every
 * pending step with its due date and a checkbox to tick, and showing the same item twice
 * where only one of them can be acted on is worse than showing it once.
 *
 * Skipping counts as settled. It is a decision somebody made at a moment, which is exactly
 * the kind of thing a history is for.
 */
export function steppedAt(step: RoadmapStep): { at: string; settled: true } | null {
  return step.completed_at ? { at: step.completed_at, settled: true } : null;
}

/**
 * The escalations inside a transcript.
 *
 * Read out of the stored tool calls rather than from a column, because there is no column:
 * `suggest_new_diagnosis` writes to an in-memory dict that becomes `ChatReply.escalated` and
 * is never persisted. What *is* persisted is the assistant message's tool calls, with their
 * arguments stored whole — so the reason survives, and this is a read rather than a record.
 */
export function escalationsIn(messages: Message[]): TimelineEvent[] {
  const found: TimelineEvent[] = [];

  for (const message of messages) {
    for (const [index, call] of (message.tool_calls ?? []).entries()) {
      if (call.name !== ESCALATION_TOOL) continue;
      const reason = typeof call.args?.reason === "string" ? call.args.reason : "";
      found.push({
        kind: "escalation",
        // The message carries the identity; a turn could in principle call the tool more
        // than once, so the index keeps the keys distinct without inventing an id.
        id: `${message.id}:${index}`,
        at: message.created_at,
        reason,
      });
    }
  }

  return found;
}

/** Whether this observation has weather worth drawing. */
export function seriesOf(observation: Observation): WeatherSummary | null {
  // An empty window is not the same as no window, but neither is worth a chart: `days` is
  // empty on a summary stored before the series was kept, which still carries aggregates
  // that a chart cannot show.
  return observation.weather?.days?.length ? observation.weather : null;
}

/**
 * Everything that happened to this plant, newest first.
 *
 * Newest first because the question a history answers — is this getting better? — is asked
 * from the present looking back, and the most recent events are the ones that answer it.
 *
 * `messages` is optional: the transcript is a second request, and the timeline renders
 * without it and gains escalations when it arrives rather than waiting for both.
 */
export function timelineOf({
  observations,
  diagnoses,
  steps,
  messages = [],
}: {
  observations: Observation[];
  diagnoses: Diagnosis[];
  steps: RoadmapStep[];
  messages?: Message[];
}): TimelineEvent[] {
  const events: TimelineEvent[] = [
    ...observations.map((observation): TimelineEvent => {
      const { at, dated } = observedAt(observation);
      return { kind: "observation", id: observation.id, at, dated, observation };
    }),
    ...diagnoses.map(
      (diagnosis): TimelineEvent => ({
        kind: "diagnosis",
        id: diagnosis.id,
        at: diagnosis.created_at,
        diagnosis,
      }),
    ),
    ...steps.flatMap((step): TimelineEvent[] => {
      const settled = steppedAt(step);
      return settled ? [{ kind: "step", id: step.id, at: settled.at, step }] : [];
    }),
    ...escalationsIn(messages),
  ];

  // Ties broken by id so the order is stable between renders. Two events genuinely sharing
  // an instant — a diagnosis and the observation it was made from, on a fast run — would
  // otherwise swap places depending on how the sort happened to be implemented.
  return events.sort(
    (a, b) => Date.parse(b.at) - Date.parse(a.at) || a.id.localeCompare(b.id),
  );
}
