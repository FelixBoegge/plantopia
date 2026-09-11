import { useId } from "react";

import type { SpeciesCandidate } from "@/api/types";

/**
 * Which plant this is, when the methods did not agree.
 *
 * Shown only when there is a decision to make. Where every method — and the owner, if they
 * said anything — named the same plant, `IdentifiedAs` says so instead: nobody is asked
 * to confirm what nobody disputed, but the pause should not go silent about what this
 * plant is going to be recorded as either.
 *
 * **Each answer says how it was reached, not which product reached it.** "Read from your
 * photo" and "matched against a plant database" mean something to a person holding a plant;
 * the names of the two systems involved do not. The attribution Pl@ntNet's terms require
 * appears below, on this same surface, whenever one of its results is on screen.
 *
 * The agreement case is the one exception, and names Pl@ntNet. Two methods sharing no
 * mechanism and reaching the same answer is the strongest thing this step can say, and
 * "a plant database" left an owner unable to tell that from a single check. See `EVIDENCE`.
 *
 * Nothing here is required. Somebody who does not know can leave it alone, and the run
 * proceeds on the leading candidate — recorded as unconfirmed, so a wrong diagnosis stays
 * attributable afterwards.
 */

/** How each answer was arrived at, in words an owner can weigh. */
export const EVIDENCE: Record<SpeciesCandidate["method"], string> = {
  typed: "What you told us",
  vision: "Read from your photo",
  plantnet: "Matched against a plant database",
  // Names Pl@ntNet, where the other three do not name anything. A deliberate exception to
  // the rule above rather than an erosion of it: "a plant database" left an owner unable to
  // tell one check from two, and agreement between two methods that share no mechanism is
  // the strongest signal this step has — it is *why* the confidence beside it reads high,
  // so it earns the words. Naming the service costs nothing here either, its attribution
  // already being on this surface whenever one of its results is.
  //
  // Safe from inconsistency by construction: `identify._merged` collapses agreement into
  // this single candidate, so `agreed` never appears beside `vision` or `plantnet` and no
  // list ever describes the same source two ways. `agreed` shows only with `typed`, or
  // alone.
  //
  // Still "your photo" rather than "the vision model": the owner took the photograph, and
  // which model read it is not a fact they can weigh.
  agreed: "Your photo and Pl@ntNet's database independently agree",
  // The strongest of the three: the owner's own guess landed on the same plant the other
  // two had already, independently, agreed on. Named in full for exactly the same reason
  // `agreed` is — this is the moment the words carry the most, not the one to be vaguest
  // about.
  all_agree: "You, your photo, and Pl@ntNet's database all agree",
};

/**
 * Confidence in words.
 *
 * A bare "0.63" invites being read as a measurement of how right the answer is, which it is
 * not — it is one system's estimate on a scale that means nothing next to the other's. The
 * words are deliberately vague for the same reason.
 */
export function confidenceText(confidence: number): string {
  if (confidence >= 0.8) return "very confident";
  if (confidence >= 0.6) return "fairly confident";
  if (confidence >= 0.4) return "not very confident";
  return "little more than a guess";
}

/**
 * How sure a candidate is, in words — two figures where both are known.
 *
 * An agreed or all-agree candidate blends vision and Pl@ntNet into whichever was higher;
 * showing only that number would discard what each method actually said in favour of the
 * more flattering half. Nothing for what somebody typed: they are not estimating a
 * likelihood, they are telling you what their plant is.
 */
export function confidenceLine(candidate: SpeciesCandidate): string | null {
  if (candidate.method === "typed") return null;
  if (
    candidate.vision_confidence != null &&
    candidate.plantnet_confidence != null
  ) {
    return `${confidenceText(candidate.vision_confidence)} from your photo, ${confidenceText(candidate.plantnet_confidence)} from Pl@ntNet`;
  }
  return confidenceText(candidate.confidence);
}

/** Whether anything on screen came from the service that must be credited. */
export function creditsPlantnet(candidates: SpeciesCandidate[]): boolean {
  return candidates.some(
    (candidate) =>
      candidate.method === "plantnet" ||
      candidate.method === "agreed" ||
      candidate.method === "all_agree",
  );
}

export function Identification({
  candidates,
  chosen,
  onChoose,
}: {
  candidates: SpeciesCandidate[];
  /** The one selected, which starts as the leading candidate. */
  chosen: SpeciesCandidate;
  onChoose: (candidate: SpeciesCandidate) => void;
}) {
  const name = useId();

  return (
    <section aria-labelledby="identification" className="grid gap-3">
      <h3 id="identification" className="font-medium">
        Which plant is this?
      </h3>

      <p className="text-muted-foreground text-sm">
        {/* Said plainly rather than implied by a preselected option. Somebody who does not
            know which is right should be able to tell that not knowing is allowed. */}
        These do not agree. Pick the one you think is right, or leave it as it
        is.
      </p>

      {/* A radiogroup rather than a listbox: one choice from a few, all visible, each with
          two lines of explanation that a select element cannot show. */}
      <div
        role="radiogroup"
        aria-labelledby="identification"
        className="grid gap-2"
      >
        {candidates.map((candidate) => {
          const selected = candidate === chosen;
          return (
            <label
              key={`${candidate.method}-${candidate.common_name}`}
              className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm ${
                // The border and the background carry the same fact the radio does. The
                // radio is what a screen reader reads and what makes the selection legible
                // without colour at all.
                selected ? "border-primary bg-muted" : "border-input"
              }`}
            >
              <input
                type="radio"
                name={name}
                className="mt-1"
                checked={selected}
                onChange={() => onChoose(candidate)}
              />
              <span className="grid gap-0.5">
                <span className="font-medium">{candidate.common_name}</span>
                {candidate.scientific_name ? (
                  <span className="text-muted-foreground italic">
                    {candidate.scientific_name}
                  </span>
                ) : null}
                <span className="text-muted-foreground">
                  {EVIDENCE[candidate.method]}
                  {/* No confidence for what somebody typed. They are not estimating a
                      likelihood, they are telling you what their plant is, and dressing
                      that up as a score would invent a measurement. */}
                  {confidenceLine(candidate)
                    ? `, ${confidenceLine(candidate)}`
                    : null}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      {creditsPlantnet(candidates) ? (
        <p className="text-muted-foreground text-xs">
          {/* A condition of the free tier, not a courtesy — and tied to the data being on
              screen rather than to this page, so a surface that shows a result cannot omit
              the credit for it. */}
          Identification powered by Pl@ntNet
        </p>
      ) : null}
    </section>
  );
}
