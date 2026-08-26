import { useEvaluation } from "@/api/hooks/account";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";

/**
 * What the evaluation harness last measured.
 *
 * Renders a file somebody produced by running a command; it does not run anything. A
 * harness run costs real money and takes minutes, which makes starting one a different kind
 * of thing from reading a result.
 *
 * Reachable only by an account permitted to see it, and refused with a 404 — which arrives
 * here as an ordinary not-found, because a screen that distinguished "you may not" from
 * "there is nothing here" would tell a stranger the route exists.
 */
export function Evaluation() {
  const { data, isPending, error } = useEvaluation();

  // The heading is outside the branches rather than inside the one that succeeds. A screen
  // whose failure state has no first-level heading is a screen somebody navigating by
  // headings arrives at and finds nothing — and it is the state a refused account always
  // sees. Nothing is disclosed by it: they typed the route to get here.
  return (
    <div className="grid max-w-3xl gap-6">
      <h1 className="text-2xl font-semibold">Evaluation</h1>

      {isPending ? (
        <p role="status">Loading…</p>
      ) : error ? (
        <Notice tone="failure" title="Not available">
          {readable(error)}
        </Notice>
      ) : (
        <>
          {!data?.results ? (
            <Notice title="No results yet">
              {/* The ordinary state of a fresh clone. Failing here would send somebody looking
                  for a bug instead of a command. */}
              Nothing has been measured yet. Run{" "}
              <code>uv run python -m eval.run_eval</code> and this will show what it
              found.
            </Notice>
          ) : (
            <>
              <p className="text-muted-foreground text-sm">
                Measured {new Date(data.generated_at ?? "").toLocaleString()}.
              </p>
              <Accuracy results={data.results} />
              {/* The rest of a harness result is a report somebody reads, not an interface
                  anything branches on. Rendering each field would be a second copy of the
                  harness's format to keep in step. */}
              <details>
                <summary className="cursor-pointer text-sm font-medium">
                  Everything measured
                </summary>
                <pre className="bg-muted mt-2 overflow-x-auto rounded-md p-4 text-xs">
                  {JSON.stringify(data.results, null, 2)}
                </pre>
              </details>
            </>
          )}
        </>
      )}
    </div>
  );
}

function Accuracy({ results }: { results: Record<string, unknown> }) {
  const accuracy = results.accuracy as Record<string, number> | undefined;
  if (!accuracy) return null;

  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {Object.entries(accuracy).map(([name, value]) => (
        <div key={name} className="rounded-md border p-3">
          <dt className="text-muted-foreground text-xs">
            {name.replace(/_/g, " ")}
          </dt>
          <dd className="text-lg font-medium">
            {typeof value === "number"
              ? `${Math.round(value * 100)}%`
              : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
