import type { Step } from "@/api/hooks/useRunStream";

/**
 * The agent working, step by step.
 *
 * This is the thing this project is best at and the thing a spinner hid for months. A
 * spinner over ninety seconds says only that nothing has crashed yet.
 *
 * `aria-live="polite"` because these arrive without a navigation: somebody who cannot see
 * the screen has no other way to know anything is happening.
 */
export function Reasoning({
  steps,
  working,
  connected,
}: {
  steps: Step[];
  working: boolean;
  connected: boolean;
}) {
  return (
    <section aria-labelledby="progress" className="grid gap-3">
      <h2 id="progress" className="text-lg font-medium">
        What Plantopia is doing
      </h2>

      <ol aria-live="polite" className="grid gap-2">
        {steps.map((step) => (
          <li key={step.sequence} className="grid gap-0.5 text-sm">
            <span>{step.description}</span>
            {step.calls || step.duration_ms !== undefined ? (
              <span className="text-muted-foreground text-xs">
                {step.calls}
                {step.calls && step.duration_ms !== undefined ? " · " : null}
                {/* "took", not "in": this is the step's wall time with the graph's overhead
                    in it, and it must not read as the model's own latency. */}
                {step.duration_ms !== undefined
                  ? `took ${(step.duration_ms / 1000).toFixed(1)}s`
                  : null}
              </span>
            ) : null}
          </li>
        ))}
        {working ? (
          <li className="text-muted-foreground text-sm">
            {/* A long step is still a step. Silence here would read as a stall, and the
                slowest part of a run is one model call that can take a minute. */}
            {connected ? "Working…" : "Reconnecting…"}
          </li>
        ) : null}
      </ol>
    </section>
  );
}
