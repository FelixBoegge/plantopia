/**
 * Query keys, in one place.
 *
 * A key typed inline at a call site is a key that will one day disagree with the one a
 * mutation invalidates — and the symptom is a screen that shows stale data until somebody
 * reloads, which is easy to miss and hard to attribute.
 */

export const keys = {
  account: ["account"] as const,
  plants: ["plants"] as const,
  plant: (id: string) => ["plants", id] as const,
  messages: (plantId: string) => ["plants", plantId, "messages"] as const,
  diagnosis: (id: string) => ["diagnoses", id] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  facts: ["profile", "facts"] as const,
  evaluation: ["evaluation", "latest"] as const,
};
