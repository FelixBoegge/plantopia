/**
 * What goes on the line under a plant's name.
 *
 * Both lines said the same thing on every plant. `plants.species` holds the *common* name
 * and the plant's own name is that same string unless somebody typed a different one — so
 * "Golden pothos" appeared twice, the second time in the italics a binomial would have
 * used. The scientific name was never stored at all (fixed alongside this).
 */

import { describe, expect, it } from "vitest";

import { speciesLine } from "@/screens/plants/species";

const plant = (fields: Partial<Parameters<typeof speciesLine>[0]>) =>
  ({
    name: "Golden pothos",
    species: null,
    species_scientific: null,
    ...fields,
  }) as Parameters<typeof speciesLine>[0];

describe("the line under a plant's name", () => {
  it("is the binomial when one is known", () => {
    const line = speciesLine(
      plant({
        species: "Golden pothos",
        species_scientific: "Epipremnum aureum",
      }),
    );

    expect(line).toBe("Epipremnum aureum");
  });

  it("is nothing when the common name only repeats the plant's name", () => {
    // The bug as seen: an identified plant the wizard named after its own species.
    const line = speciesLine(
      plant({ name: "Golden pothos", species: "Golden pothos" }),
    );

    expect(line).toBeNull();
  });

  it("is the common name when it says something the name does not", () => {
    // Somebody renamed the plant. Then the species is a second fact, not an echo.
    const line = speciesLine(
      plant({ name: "Kitchen pot", species: "Golden pothos" }),
    );

    expect(line).toBe("Golden pothos");
  });

  it("ignores case and surrounding space when deciding that", () => {
    const line = speciesLine(
      plant({ name: "  golden pothos ", species: "Golden Pothos" }),
    );

    expect(line).toBeNull();
  });

  it("prefers the binomial even when the common name would also have shown", () => {
    // Two facts, one line. The binomial is the one the name cannot already be carrying.
    const line = speciesLine(
      plant({
        name: "Kitchen pot",
        species: "Golden pothos",
        species_scientific: "Epipremnum aureum",
      }),
    );

    expect(line).toBe("Epipremnum aureum");
  });

  it("is nothing for a plant nobody has identified", () => {
    expect(speciesLine(plant({}))).toBeNull();
  });
});
