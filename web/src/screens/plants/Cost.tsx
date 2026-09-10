import type { Diagnosis } from "@/api/types";

/**
 * What Plantopia has spent understanding this plant, summed across every diagnosis
 * on it.
 *
 * `cost_usd` and `token_usage` are each nullable on their own — a failed run records
 * no cost, and neither does any diagnosis made before either was kept — so a single
 * diagnosis can carry one without the other. Summed independently rather than
 * defaulting a missing one to zero, which would silently understate the total and
 * read as though it were the whole answer.
 */
export function TotalCost({ diagnoses }: { diagnoses: Diagnosis[] }) {
  const costs = diagnoses
    .map((diagnosis) => diagnosis.cost_usd)
    .filter((cost): cost is number => cost !== null);
  const usages = diagnoses
    .map((diagnosis) => diagnosis.token_usage)
    .filter((usage): usage is TokenUsage => usage !== null);

  if (costs.length === 0 && usages.length === 0) {
    return (
      <section aria-labelledby="cost">
        <h2 id="cost" className="mb-3 text-lg font-medium">
          What this has cost
        </h2>
        <p className="text-muted-foreground text-sm">Not yet measured.</p>
      </section>
    );
  }

  const totalTokens = usages.reduce(
    (sum, usage) => sum + usage.total_tokens,
    0,
  );
  const promptTokens = usages.reduce(
    (sum, usage) => sum + usage.prompt_tokens,
    0,
  );
  const completionTokens = usages.reduce(
    (sum, usage) => sum + usage.completion_tokens,
    0,
  );
  const totalCost = costs.reduce((sum, cost) => sum + cost, 0);

  const parts: string[] = [];
  if (usages.length > 0) {
    parts.push(
      `${totalTokens.toLocaleString()} tokens (${promptTokens.toLocaleString()} prompt, ${completionTokens.toLocaleString()} completion)`,
    );
  }
  // Four places: real costs here are fractions of a cent, and "$0.00" would claim a
  // measured run was free — the same reasoning the API's own `cost_usd` docstring
  // already states.
  if (costs.length > 0) {
    parts.push(`$${totalCost.toFixed(4)}`);
  }

  // Either field can be missing on any diagnosis independently, so "some of this
  // total is missing a measurement" is its own fact, distinct from "there is no
  // total at all" above.
  const incomplete =
    costs.length < diagnoses.length || usages.length < diagnoses.length;

  return (
    <section aria-labelledby="cost">
      <h2 id="cost" className="mb-3 text-lg font-medium">
        What this has cost
      </h2>
      <p>{parts.join(" — ")}</p>
      {incomplete ? (
        <p className="text-muted-foreground text-xs">
          Not every diagnosis on this plant recorded a full measurement; the
          total above covers only what was.
        </p>
      ) : null}
    </section>
  );
}

type TokenUsage = NonNullable<Diagnosis["token_usage"]>;
