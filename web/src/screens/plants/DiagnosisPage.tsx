import { Link, useParams } from "react-router-dom";

import { useDiagnosis } from "@/api/hooks/runs";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
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
      <Differential detail={data} />
      <Link
        to={`/plants/${data.diagnosis.plant_id}`}
        className="text-sm underline underline-offset-4"
      >
        Back to this plant
      </Link>
    </div>
  );
}
