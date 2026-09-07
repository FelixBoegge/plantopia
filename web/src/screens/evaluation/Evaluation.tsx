import { useEvaluation } from "@/api/hooks/account";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import {
  CategoryBars,
  Hero,
  Meter,
  StatTile,
  count,
  percent,
} from "@/screens/evaluation/Figures";
import {
  readReport,
  type Metric,
  type Provenance,
  type Report,
  type Stability,
} from "@/screens/evaluation/report";

/**
 * What the evaluation harness last measured.
 *
 * Renders a file somebody produced by running a command; it does not run anything. A
 * harness run costs real money and takes minutes, which makes starting one a different kind
 * of thing from reading a result.
 *
 * Reachable only by an account the server says may read it, and refused with a 404 — which
 * arrives here as an ordinary not-found, because a screen that distinguished "you may not"
 * from "there is nothing here" would tell a stranger the route exists.
 *
 * **It used to show four tiles and a JSON dump.** The tiles came from mapping over every
 * key in `accuracy` and multiplying each by 100, so `scored: 28` read as "2800%" and
 * `by_category` as "[object Object]"; the dump was the rest of the file, unreadable. What
 * that arrangement got right was refusing to duplicate the harness's format on the screen —
 * and `report.ts` is the answer to that, reading each section defensively so a harness
 * change costs a panel rather than the page.
 *
 * Every section renders only if its data is there. A result this page does not recognise is
 * a shorter page, never a broken one.
 */
export function Evaluation() {
  const { data, isPending, error } = useEvaluation();

  // The heading is outside the branches rather than inside the one that succeeds. A screen
  // whose failure state has no first-level heading is a screen somebody navigating by
  // headings arrives at and finds nothing — and it is the state a refused account always
  // sees. Nothing is disclosed by it: they typed the route to get here.
  return (
    <div className="grid max-w-4xl gap-8">
      <h1 className="text-2xl font-semibold">RAG Evaluation Report</h1>

      {isPending ? (
        <p role="status">Loading…</p>
      ) : error ? (
        <Notice tone="failure" title="Not available">
          {readable(error)}
        </Notice>
      ) : !data?.results ? (
        <Notice title="No results yet">
          {/* The ordinary state of a fresh clone. Failing here would send somebody looking
              for a bug instead of a command. */}
          Nothing has been measured yet. Run{" "}
          <code>uv run python -m eval.run_eval</code> and this will show what it
          found.
        </Notice>
      ) : (
        <Result
          generatedAt={data.generated_at}
          report={readReport(data.results)}
        />
      )}
    </div>
  );
}

function Result({
  generatedAt,
  report,
}: {
  generatedAt: string | null;
  report: Report;
}) {
  const { accuracy } = report;

  return (
    <>
      <p className="text-muted-foreground text-sm">
        Measured{" "}
        {generatedAt
          ? new Date(generatedAt).toLocaleString()
          : "at an unrecorded time"}
        . Every figure here comes from one run of the harness over the golden
        set; nothing on this page is live.
      </p>

      {accuracy ? (
        <section aria-labelledby="accuracy" className="grid gap-6">
          <h2 id="accuracy" className="text-lg font-medium">
            Did it name the right disorder?
          </h2>

          <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:items-start">
            <Hero
              value={percent(accuracy.top1)}
              label="Correct at rank one"
              detail={`${accuracy.top1Cases} of ${accuracy.scored} cases led with the right disorder`}
            />
            <dl className="grid gap-3 sm:grid-cols-3">
              <StatTile
                label="Within the top three"
                value={percent(accuracy.top3)}
                detail="The right disorder appeared somewhere in the differential"
              />
              {/* Counts, not rates. This is the pair the old page rendered as "2800%" and
                  "0%" by multiplying everything in `accuracy` by a hundred. */}
              <StatTile
                label="Cases scored"
                value={count(accuracy.scored)}
                detail={
                  accuracy.failed
                    ? `${count(accuracy.failed)} could not be scored`
                    : "none failed to run"
                }
              />
              {report.nearMisses === null ? null : (
                <StatTile
                  label="Near misses"
                  value={count(report.nearMisses)}
                  detail="Right disorder ranked second or third"
                />
              )}
            </dl>
          </div>

          {accuracy.byCategory.length ? (
            <div className="grid gap-3">
              <h3 className="text-sm font-medium">
                By category, weakest first
                <span className="text-muted-foreground font-normal">
                  {" "}
                  — bars are the rank-one rate
                </span>
              </h3>
              <CategoryBars categories={accuracy.byCategory} />
            </div>
          ) : null}
        </section>
      ) : null}

      {report.metrics.length ? <Metrics metrics={report.metrics} /> : null}
      {report.stability ? (
        <StabilitySection stability={report.stability} />
      ) : null}
      {report.cases.length ? <Cases report={report} /> : null}
      {report.provenance ? <Provenance provenance={report.provenance} /> : null}
    </>
  );
}

/**
 * The four Ragas measures.
 *
 * Each gets its meaning in words, because a reader who does not already know what context
 * precision is cannot act on 54%. Each also gets its coverage: `M22` records a run where
 * this metric timed out on every row and scored 0 of 28 while the other three scored all of
 * them, and a value whose denominator is hidden cannot be told apart from that.
 */
function Metrics({ metrics }: { metrics: Metric[] }) {
  return (
    <section aria-labelledby="ragas" className="grid gap-4">
      <div className="grid gap-1">
        <h2 id="ragas" className="text-lg font-medium">
          How good was the retrieval and the answer?
        </h2>
        <p className="text-muted-foreground text-sm">
          Judged by a model reading each case, not by string comparison. All
          four run from 0 to 1.
        </p>
      </div>

      <dl className="grid gap-4 sm:grid-cols-2">
        {metrics.map((metric) => (
          <div
            key={metric.key}
            className="grid content-start gap-2 rounded-md border p-4"
          >
            <div className="flex items-baseline justify-between gap-3">
              <dt className="font-medium">{metric.label}</dt>
              <dd className="text-lg font-semibold tabular-nums">
                {percent(metric.value)}
              </dd>
            </div>
            <Meter value={metric.value} />
            <p className="text-muted-foreground text-sm">{metric.meaning}</p>
            {metric.scored !== null && metric.total !== null ? (
              <p className="text-muted-foreground text-xs">
                Scored on {metric.scored} of {metric.total} cases
                {metric.scored < metric.total
                  ? " — the rest could not be judged, so the figure covers less than the set"
                  : ""}
                .
              </p>
            ) : null}
            {metric.caveat ? (
              <p className="text-muted-foreground border-l pl-3 text-xs">
                {metric.caveat}
              </p>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * How much the same case moves between runs.
 *
 * **Two of the three read better when they are lower**, which is stated in words on each
 * one. Colour cannot carry that: a status hue is reserved for state and would need an icon
 * and a label anyway, and painting churn red would assert a threshold nobody has set.
 */
function StabilitySection({ stability }: { stability: Stability }) {
  return (
    <section aria-labelledby="stability" className="grid gap-4">
      <div className="grid gap-1">
        <h2 id="stability" className="text-lg font-medium">
          Does it say the same thing twice?
        </h2>
        <p className="text-muted-foreground text-sm">
          {stability.cases !== null && stability.runsPerCase !== null
            ? `Measured by running ${stability.cases} cases ${stability.runsPerCase} times each.`
            : "Measured by running a subset of cases repeatedly."}
        </p>
      </div>

      <dl className="grid gap-4 sm:grid-cols-3">
        {stability.measures.map((measure) => (
          <div
            key={measure.key}
            className="grid content-start gap-2 rounded-md border p-4"
          >
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-sm font-medium">{measure.label}</dt>
              <dd className="text-lg font-semibold tabular-nums">
                {percent(measure.value)}
              </dd>
            </div>
            <Meter value={measure.value} />
            <p className="text-muted-foreground text-xs">
              {measure.higherIsBetter
                ? "Higher is better."
                : "Lower is better."}{" "}
              {measure.meaning}
            </p>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Every case, and what became of it. The list the JSON dump was hiding. */
function Cases({ report }: { report: Report }) {
  return (
    <section aria-labelledby="cases" className="grid gap-4">
      <div className="grid gap-1">
        <h2 id="cases" className="text-lg font-medium">
          Every case
        </h2>
        <p className="text-muted-foreground text-sm">
          The golden set, one row each.
          {report.retriedCases.length
            ? ` ${report.retriedCases.length} needed a second attempt after a failure that was not about the diagnosis.`
            : " None needed a second attempt."}
        </p>
      </div>

      {/* Its own scroll container, so a narrow screen scrolls the table rather than the
          page sideways. */}
      <div className="overflow-x-auto">
        {/* `min-w` as well as `w-full`: without a floor the table shrinks to its
            container instead of overflowing it, and on a phone every column compressed to
            about three characters — the scroll container above had nothing to scroll.
            Found by looking at it at 390px, not by any test. */}
        <table className="w-full min-w-[46rem] text-sm">
          <thead>
            <tr className="text-muted-foreground border-b text-left">
              <th scope="col" className="py-2 pr-3 font-medium">
                Case
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Category
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Should have said
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Led with
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Result
              </th>
              <th scope="col" className="py-2 text-right font-medium">
                Questions
              </th>
            </tr>
          </thead>
          <tbody>
            {report.cases.map((row) => (
              <tr key={row.id} className="border-b align-top last:border-0">
                <td className="py-2 pr-3">{row.id}</td>
                <td className="text-muted-foreground py-2 pr-3 capitalize">
                  {row.category ?? "—"}
                </td>
                <td className="py-2 pr-3">{row.groundTruth}</td>
                <td className="py-2 pr-3">{row.candidates[0] ?? "—"}</td>
                <td className="py-2 pr-3 whitespace-nowrap">
                  {/* In words, never in colour alone — and the words are the fact rather
                      than a verdict on it. */}
                  {row.error
                    ? `Did not run — ${row.error}`
                    : row.top1Hit
                      ? "Correct at rank one"
                      : row.top3Hit
                        ? "Correct within three"
                        : "Missed"}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {row.questionsAsked}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** What produced these numbers. Without it a figure cannot be compared with another run. */
function Provenance({ provenance }: { provenance: Provenance }) {
  const rows: [string, string][] = [
    ["Reasoning model", provenance.reasoningModel ?? "—"],
    ["Vision model", provenance.visionModel ?? "—"],
    ["Embedding model", provenance.embeddingModel ?? "—"],
    [
      "Temperature",
      provenance.temperature === null ? "—" : String(provenance.temperature),
    ],
    [
      "Corpus",
      provenance.corpusDocuments === null
        ? "—"
        : `${provenance.corpusDocuments} disorder documents`,
    ],
    [
      "Golden set",
      provenance.goldenSetSize === null
        ? "—"
        : `${provenance.goldenSetSize} cases`,
    ],
    ["Owner profile", provenance.profile ?? "—"],
    [
      "Tokens",
      provenance.totalTokens === null ? "—" : count(provenance.totalTokens),
    ],
    [
      "Cost",
      provenance.costUsd === null ? "—" : `$${provenance.costUsd.toFixed(2)}`,
    ],
  ];

  return (
    <section aria-labelledby="provenance" className="grid gap-4">
      <h2 id="provenance" className="text-lg font-medium">
        What produced these numbers
      </h2>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="grid gap-0.5 sm:col-span-2 sm:grid-cols-subgrid"
          >
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
