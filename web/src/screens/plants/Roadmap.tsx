import { useMarkStep } from "@/api/hooks/plants";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { Checkbox } from "@/components/ui/checkbox";
import type { RoadmapStep } from "@/api/types";

/**
 * The plan, as a checklist somebody works through.
 *
 * Ticking a step is a request, not a local toggle. The count on the plant grid is derived
 * from the same rows, so a checkbox that only changed itself would leave the grid saying
 * three steps remain while this screen showed two.
 */
export function Roadmap({
  plantId,
  steps,
}: {
  plantId: string;
  steps: RoadmapStep[];
}) {
  const mark = useMarkStep(plantId);

  if (steps.length === 0) return null;

  return (
    <section aria-labelledby="plan">
      <h2 id="plan" className="mb-3 text-lg font-medium">
        Treatment road map
      </h2>

      {mark.error ? (
        <Notice tone="failure">{readable(mark.error)}</Notice>
      ) : null}

      <ul className="grid gap-3">
        {[...steps]
          .sort((a, b) => a.ordinal - b.ordinal)
          .map((step) => (
            <li
              key={step.id}
              className="flex items-start gap-3 rounded-md border p-3"
            >
              <Checkbox
                checked={step.status === "done"}
                aria-label={step.action}
                onCheckedChange={(checked) =>
                  // Reopening clears the completion. A step marked done and then reopened
                  // has not been done, and a date saying otherwise is a lie the history
                  // repeats.
                  mark.mutate({
                    stepId: step.id,
                    status: checked === true ? "done" : "pending",
                  })
                }
              />
              <div className="grid gap-1">
                <span
                  className={
                    step.status === "done" ? "line-through" : undefined
                  }
                >
                  {step.action}
                </span>
                <span className="text-muted-foreground text-sm">
                  {step.rationale}
                </span>
                <span className="text-muted-foreground text-xs">
                  You will know it worked when: {step.success_signal}
                </span>
                {step.status === "done" && step.completed_at ? (
                  <span className="text-muted-foreground text-xs">
                    Done {new Date(step.completed_at).toLocaleDateString()}
                  </span>
                ) : null}
              </div>
            </li>
          ))}
      </ul>
    </section>
  );
}
