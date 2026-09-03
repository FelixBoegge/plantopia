import { Link, useParams } from "react-router-dom";

import { useActivity, useDiagnosis } from "@/api/hooks/runs";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { StepLine } from "@/components/StepLine";
import { Differential } from "@/screens/wizard/Differential";

/**
 * One diagnosis, in full.
 *
 * This route was missing. `PlantDetail` has linked to `/diagnoses/:id` since the React
 * frontend landed, and nothing served it — the link fell through to the catch-all and
 * silently redirected to the plants list. Every test checked the `href` and none of them
 * followed it, so it looked right everywhere and worked nowhere. A browser test written for
 * the timeline found it by being the first thing to click it.
 *
 * The parts all existed: the endpoint, the `useDiagnosis` hook, and `<Differential>`, which
 * takes exactly the shape the endpoint returns. Only the route was absent.
 */
export function DiagnosisPage() {
  const { diagnosisId = "" } = useParams();
  const { data, isPending, error } = useDiagnosis(diagnosisId || null);
  // Its own request, and its own failure. A panel describing how the result was reached is
  // not worth losing the result over, so nothing here branches on its error.
  const { data: activity } = useActivity(diagnosisId || null);

  if (isPending) return <p role="status">Loading…</p>;

  if (error) {
    return (
      <Notice tone="failure" title="This diagnosis could not be loaded">
        {readable(error)}
      </Notice>
    );
  }

  if (!data) return null;

  return (
    <div className="grid gap-6">
      {/* Above the result, not below it. A diagnosis runs to a differential, a plan and an
          activity log, and a way back that only appears after all of it is a way back
          somebody has to scroll to find. */}
      <Link
        to={`/plants/${data.diagnosis.plant_id}`}
        className="text-muted-foreground w-fit text-sm underline underline-offset-4"
      >
        Back to this plant
      </Link>

      <Differential detail={data} />

      {/* Only when there is something to show. Every diagnosis reached before any of this
          was recorded has no activity, and a heading over an empty list reads as a failure
          rather than as an absence. */}
      {activity?.length ? (
        <section aria-labelledby="how" className="grid gap-3">
          <h2 id="how" className="text-lg font-medium">
            How this was reached
          </h2>
          <ol className="grid gap-2">
            {activity.map((step) => (
              <li key={step.sequence} className="grid gap-0.5 text-sm">
                <StepLine step={step} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
