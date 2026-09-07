import type { Step } from "@/api/hooks/useRunStream";
import { StepLine } from "@/components/StepLine";

/**
 * The agent working, step by step.
 *
 * This is the thing this project is best at and the thing a spinner hid for months. A
 * spinner over ninety seconds says only that nothing has crashed yet.
 *
 * **Which is an argument against a spinner *instead of* this list, not against the one on
 * the trailing line.** The steps are still the substance; the spinner animates the "still
 * working" line that was already there, and only while a step is in flight. It exists
 * because the list is silent for the length of a single model call, and a minute of an
 * unchanging list reads as a page that has died.
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
            <StepLine step={step} />
          </li>
        ))}
        {working ? (
          <li className="text-muted-foreground flex items-center gap-2 text-sm">
            {/* A long step is still a step. Silence here would read as a stall, and the
                slowest part of a run is one model call that can take a minute — during
                which the list above does not change at all.

                The spinner is decorative: `aria-hidden`, because the text beside it
                already carries the meaning and the whole list is a live region that
                announces it. A spinner with a name of its own is announced twice and says
                nothing either time.

                `motion-reduce:animate-none` rather than hiding it for somebody who asked
                motion to stop — a still ring says "there is something here and it has not
                finished", which is the entire message. */}
            <span
              data-testid="processing-spinner"
              aria-hidden="true"
              className="size-3 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
            />
            {connected ? "Processing" : "Reconnecting…"}
          </li>
        ) : null}
      </ol>
    </section>
  );
}
