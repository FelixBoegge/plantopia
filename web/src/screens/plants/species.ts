import type { Plant } from "@/api/types";

/**
 * What belongs on the line under a plant's name, or nothing.
 *
 * **Both lines used to say the same thing.** The wizard does not ask for a name — naming a
 * plant before finding out what it is is the wrong way round — so it falls back to the
 * identified species, and `plants.species` holds the *common* name. An identified plant
 * therefore had its own name written twice, the second time in the italics a scientific
 * name would have used. The binomial that would have filled that line was collected by the
 * vision model, corroborated by Pl@ntNet, and discarded for want of a column.
 *
 * With the column in place the rule is: the binomial when there is one, because it is the
 * fact the name above cannot already be carrying. Failing that, the common name — but only
 * when it differs from the name, which is what stops the duplication for the plants that
 * have no binomial and never will. Failing both, nothing: a second line that repeats the
 * first is worse than no second line.
 *
 * Compared case- and space-insensitively, because "Golden Pothos" under "golden pothos" is
 * the same duplication with different keystrokes.
 */
export function speciesLine(
  plant: Pick<Plant, "name" | "species" | "species_scientific">,
): string | null {
  if (plant.species_scientific) return plant.species_scientific;
  if (!plant.species) return null;

  const same = normalise(plant.species) === normalise(plant.name);
  return same ? null : plant.species;
}

function normalise(value: string): string {
  return value.trim().toLowerCase();
}
