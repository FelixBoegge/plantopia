import type { Step } from "@/api/hooks/useRunStream";

/**
 * One thing a diagnosis did, with what it called and how long it took.
 *
 * Shared by the activity beside a running diagnosis and the record on a finished one,
 * because the two showed the same thing and drifted into the same bug: **the two sources
 * spell "absent" differently.** The event stream omits the fields, so they arrive
 * `undefined`; the endpoint sends an absent optional as `null`. A check for `undefined`
 * alone passed the stream and failed the endpoint, and failed quietly — `null / 1000` is 0,
 * so every step of every diagnosis older than this feature claimed to have taken 0.0s.
 *
 * `!= null` is deliberate, and the one place loose equality earns its keep here: it is
 * exactly the "null or undefined" test this needs.
 */
export function StepLine({ step }: { step: Step }) {
  const calls = step.calls;
  const took = step.duration_ms;

  return (
    <>
      <span>{step.description}</span>
      {calls != null || took != null ? (
        <span className="text-muted-foreground text-xs">
          {calls}
          {calls != null && took != null ? " · " : null}
          {/* "took", not "in": this is the step's wall time with the graph's own overhead
              in it, and it must not read as the model's latency. */}
          {took != null ? `took ${(took / 1000).toFixed(1)}s` : null}
        </span>
      ) : null}
    </>
  );
}
