import type { WeatherSummary } from "@/api/types";

/**
 * The weather an observation was made in, drawn and tabulated.
 *
 * Hand-drawn SVG rather than a charting library: this is two line paths and a row of bars
 * over about three weeks, and the project has twelve runtime dependencies — adding a large
 * one for a single chart would be a poor trade, and would bring its own colour and
 * accessibility decisions into a codebase that has made those deliberately.
 *
 * **The chart is not the content.** `openspec/specs/web-client/spec.md` requires that colour
 * is never the only carrier of meaning, and axe runs over this route. So the same series is
 * rendered as a table — present, keyboard reachable, read by a screen reader — and the chart
 * is marked decorative. The table is the accessible representation; the chart is the fast
 * one. A rendering bug in the drawing degrades to a readable table rather than to nothing.
 *
 * The stored summary also carries a seven-day *forecast*, which is deliberately not drawn:
 * it was the week ahead of the run, which is the past by the time anybody reads a history.
 */

const FROST_C = 0;
const HEAT_C = 32;

/** Chart geometry, in user units. The viewBox scales it; nothing here is pixels. */
const WIDTH = 320;
const HEIGHT = 90;
const PAD = 4;

export function Weather({ summary }: { summary: WeatherSummary }) {
  const days = summary.days;
  if (days.length === 0) return null;

  const lows = days.map((day) => day.min_temp_c);
  const highs = days.map((day) => day.max_temp_c);
  const floor = Math.min(...lows, FROST_C);
  const ceiling = Math.max(...highs);
  const span = ceiling - floor || 1;
  const rain = Math.max(...days.map((day) => day.precip_mm), 1);

  const x = (index: number) =>
    days.length === 1 ? WIDTH / 2 : PAD + (index * (WIDTH - 2 * PAD)) / (days.length - 1);
  const y = (value: number) => HEIGHT - PAD - ((value - floor) / span) * (HEIGHT - 2 * PAD);

  const path = (values: number[]) =>
    values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index)} ${y(value)}`).join(" ");

  return (
    <figure className="grid gap-1">
      <figcaption className="text-muted-foreground text-sm">{summarise(summary)}</figcaption>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-24 w-full max-w-md"
        // Decorative: every value it shows is in the table below, which is what assistive
        // technology reads. Marking it up as a figure with its own labels would make a
        // screen reader announce the same series twice.
        role="presentation"
        aria-hidden="true"
        focusable="false"
      >
        {days.map((day, index) => (
          <rect
            key={`${day.on}-rain`}
            x={x(index) - 2}
            y={HEIGHT - PAD - (day.precip_mm / rain) * (HEIGHT / 3)}
            width={4}
            height={(day.precip_mm / rain) * (HEIGHT / 3)}
            className="fill-sky-400/50"
          />
        ))}
        {floor <= FROST_C && ceiling >= FROST_C ? (
          <line
            x1={0}
            x2={WIDTH}
            y1={y(FROST_C)}
            y2={y(FROST_C)}
            className="stroke-muted-foreground/40"
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        ) : null}
        <path d={path(highs)} fill="none" className="stroke-orange-500" strokeWidth={1.5} />
        <path d={path(lows)} fill="none" className="stroke-blue-500" strokeWidth={1.5} />
      </svg>

      <table className="sr-only">
        <caption>Daily weather while this plant was photographed</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Lowest temperature</th>
            <th scope="col">Highest temperature</th>
            <th scope="col">Rainfall</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.on}>
              <th scope="row">{day.on}</th>
              <td>{day.min_temp_c} °C</td>
              <td>{day.max_temp_c} °C</td>
              <td>{day.precip_mm} mm</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/**
 * The window in a sentence.
 *
 * Read by everybody, not only by somebody who cannot see the chart: the notable day is the
 * one that explains the plant, and finding it by eye on a 21-point line is work.
 */
export function summarise(summary: WeatherSummary): string {
  const days = summary.days;
  const last = days.at(-1);
  if (!last) return "";

  const parts = [
    `${days.length} ${days.length === 1 ? "day" : "days"} to ${last.on}`,
    `${Math.min(...days.map((day) => day.min_temp_c))} to ${Math.max(
      ...days.map((day) => day.max_temp_c),
    )} °C`,
  ];

  const frosts = days.filter((day) => day.min_temp_c <= FROST_C);
  const firstFrost = frosts.at(0);
  if (firstFrost) {
    parts.push(
      frosts.length === 1
        ? `frost on ${firstFrost.on}`
        : `frost on ${frosts.length} days, first ${firstFrost.on}`,
    );
  }

  const hot = days.filter((day) => day.max_temp_c >= HEAT_C);
  const firstHot = hot.at(0);
  if (firstHot) {
    parts.push(
      hot.length === 1
        ? `above ${HEAT_C} °C on ${firstHot.on}`
        : `${hot.length} days above ${HEAT_C} °C`,
    );
  }

  const rain = days.reduce((total, day) => total + day.precip_mm, 0);
  parts.push(`${Math.round(rain * 10) / 10} mm of rain`);

  return parts.join(", ");
}
