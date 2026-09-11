import type { SpeciesCandidate } from "@/api/types";
import {
  EVIDENCE,
  confidenceLine,
  creditsPlantnet,
} from "@/screens/wizard/Identification";

/**
 * What this plant will be recorded as, when there is nothing left to choose between.
 *
 * Every run reaches a species before it can reach anything else, and the pause used to
 * say nothing about it at all unless the methods disagreed — silence that read as this
 * step having nothing to do with identification, when the opposite was true: it had
 * already been settled, just never said. `Identification` is the sibling this stands in
 * for whenever there is one candidate rather than several — same evidence, same
 * confidence words, no radio buttons over a choice that does not exist.
 */
export function IdentifiedAs({ candidate }: { candidate: SpeciesCandidate }) {
  return (
    <section aria-labelledby="identified-as" className="grid gap-1">
      <h3 id="identified-as" className="font-medium">
        What this will be recorded as
      </h3>

      <p className="text-lg">
        <span className="font-semibold">{candidate.common_name}</span>
        {candidate.scientific_name ? (
          <span className="text-muted-foreground text-base italic">
            {" "}
            ({candidate.scientific_name})
          </span>
        ) : null}
      </p>

      <p className="text-muted-foreground text-sm">
        {EVIDENCE[candidate.method]}
        {confidenceLine(candidate) ? `, ${confidenceLine(candidate)}` : null}
      </p>

      {creditsPlantnet([candidate]) ? (
        <p className="text-muted-foreground text-xs">
          {/* A condition of the free tier, not a courtesy — see `Identification`. */}
          Identification powered by Pl@ntNet
        </p>
      ) : null}
    </section>
  );
}
