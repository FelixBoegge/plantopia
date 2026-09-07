import type { CategoryScore } from "@/screens/evaluation/report";

/**
 * The figures this report is made of.
 *
 * **No categorical palette, because nothing here has two series.** Every figure encodes one
 * measure, so magnitude is carried by length — a bar's length, a meter's fill — and one hue
 * suffices. `--chart-1` is the strongest step of the theme's sequential ramp and is
 * correctly inverted between light and dark, which is what makes both readable without a
 * second set of values. `index.css` notes that the `--chart-*` ramp is sequential and so
 * wrong for categorical series; that is exactly why there are none here.
 *
 * **No severity colour either.** A meter's fill is allowed to carry severity, but nobody has
 * set a threshold for what a bad faithfulness score is, and `M22` records that context
 * precision is structurally lower here by design. Painting 54% red would assert a standard
 * this project has not agreed and would read as a fault where the register argues there is
 * none. The words beside each figure carry the judgement instead.
 *
 * Text never wears the data colour. Values and labels use text tokens; the coloured mark
 * beside them carries the measure.
 */

/** One decimal, because 89.3% and 96.4% are the numbers the register quotes. */
export function percent(value: number): string {
  const scaled = value * 100;
  return `${Number.isInteger(scaled) ? scaled : scaled.toFixed(1)}%`;
}

/** `en-US` explicitly: every other word here is English, and a bare locale groups by
 *  whatever the runtime carries — "449.445" on a German machine. */
export function count(value: number): string {
  return value.toLocaleString("en-US");
}

/**
 * The one number the page leads with.
 *
 * Exactly one per view, ≥48px, in the same sans as everything else. Proportional figures
 * rather than tabular: at this size `tabular-nums` gives every digit the width of a zero
 * and the number reads loose.
 */
export function Hero({
  value,
  label,
  detail,
}: {
  value: string;
  label: string;
  detail: string;
}) {
  return (
    <div className="grid gap-1">
      <p className="text-muted-foreground text-sm">{label}</p>
      <p className="text-5xl leading-none font-semibold">{value}</p>
      <p className="text-muted-foreground text-sm">{detail}</p>
    </div>
  );
}

/** A headline number with its own label. No sparkline: one run is not a series. */
export function StatTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="grid content-start gap-1 rounded-md border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
      {detail ? (
        <p className="text-muted-foreground text-xs">{detail}</p>
      ) : null}
    </div>
  );
}

/**
 * A ratio against its limit.
 *
 * The track is the theme's muted surface and the fill one hue, so the whole bar reads as
 * one measure against one scale. `aria-hidden` on the bar: the value is already text beside
 * it, and a second announcement of the same number says nothing.
 */
export function Meter({ value }: { value: number }) {
  const filled = Math.max(0, Math.min(1, value));

  return (
    <div
      aria-hidden="true"
      className="bg-muted h-2 overflow-hidden rounded-full"
    >
      <div
        className="bg-chart-1 h-full rounded-r-[4px]"
        style={{ width: `${filled * 100}%` }}
      />
    </div>
  );
}

/**
 * Accuracy by category, weakest first.
 *
 * A horizontal bar per category: the job is comparing magnitude across seven named classes,
 * which is a bar chart, and the names are words so the bars run horizontally. One hue,
 * because length is doing the work.
 *
 * **Everything is labelled, so there is no tooltip.** A hover layer exists to reveal what a
 * mark does not say; here the category, its top-1 rate, its top-3 rate and its case count
 * are all in text on the row. A tooltip would repeat them.
 *
 * The case count is not decoration. Half of two cases and all of five are not comparable
 * claims, and the rate alone cannot say so.
 */
export function CategoryBars({ categories }: { categories: CategoryScore[] }) {
  return (
    // A definition list rather than a chart element: the data is text with a bar beside it,
    // which is also the table view an assistive reader gets for free.
    <dl className="grid gap-3">
      {categories.map((category) => (
        <div key={category.name} className="grid gap-1">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-sm capitalize">{category.name}</dt>
            <dd className="text-muted-foreground text-xs">
              top-3 {percent(category.top3)} · {category.scored}{" "}
              {category.scored === 1 ? "case" : "cases"}
            </dd>
          </div>
          {/* The bar and its value on one line, the value outside the bar's end. Inside
              would clip at the short end of this scale — "50.0%" does not fit in half a
              row — and a clipped label is worse than none. */}
          <div className="flex items-center gap-2">
            <div
              aria-hidden="true"
              // The baseline. A hairline, one step off the surface, recessive.
              className="bg-muted h-3 flex-1 overflow-hidden rounded-sm border-l"
            >
              <div
                className="bg-chart-1 h-full rounded-r-[4px]"
                style={{
                  width: `${Math.max(0, Math.min(1, category.top1)) * 100}%`,
                }}
              />
            </div>
            <span className="w-14 shrink-0 text-right text-sm tabular-nums">
              {percent(category.top1)}
            </span>
          </div>
        </div>
      ))}
    </dl>
  );
}
