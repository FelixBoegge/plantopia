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

// **The scales are fixed, not fitted to each chart.** A chart scaled to its own data reads
// as if every August were the same August: two windows with different weather draw the same
// shape, and a plant's history becomes a row of pictures that cannot be compared with each
// other, which is the one thing a history is for.
//
// So both axes start from a standing range with round ticks, and grow by whole steps only
// when a reading falls outside. Most charts therefore share one scale, and the ones that do
// not say so plainly with a different top number rather than lying quietly.
const TEMP_STEP = 10;
const TEMP_FLOOR = 0;
const TEMP_CEILING = 30;
const RAIN_STEP = 10;
const RAIN_CEILING = 30;

/** The lowest multiple of `step` at or below `value`. */
function down(value: number, step: number): number {
  return Math.floor(value / step) * step;
}

/** The lowest multiple of `step` at or above `value`. */
function up(value: number, step: number): number {
  return Math.ceil(value / step) * step;
}

/** Every tick from `from` to `to`, inclusive, `step` apart. */
function ticks(from: number, to: number, step: number): number[] {
  const marks: number[] = [];
  for (let value = from; value <= to; value += step) marks.push(value);
  return marks;
}

/** Chart geometry, in user units. The viewBox scales it; nothing here is pixels. */
const WIDTH = 320;
const HEIGHT = 90;
const PAD = 4;

// Room on the flanks for the two scales. Temperature reads on the left and rainfall on the
// right, because they are different units on one picture and a single axis would invite
// reading a millimetre off the degree scale.
const GUTTER_LEFT = 26;
const GUTTER_RIGHT = 24;

export function Weather({
  summary,
  capturedOn,
}: {
  summary: WeatherSummary;
  /**
   * When the photographs were taken, if the camera said.
   *
   * Marked on the chart because it is the only day in the window that the plant's state is
   * actually evidence about — the rest is what led up to it. Without it a reader has three
   * weeks of line and no idea which point the photograph belongs to.
   */
  capturedOn?: string | null;
}) {
  const days = summary.days;
  if (days.length === 0) return null;

  const onDay = (iso: string | null | undefined) => {
    if (!iso) return -1;
    const date = iso.slice(0, 10);
    return days.findIndex((day) => day.on.slice(0, 10) === date);
  };
  const captured = onDay(capturedOn);
  const today = onDay(new Date().toISOString());

  const lows = days.map((day) => day.min_temp_c);
  const highs = days.map((day) => day.max_temp_c);
  const floor = Math.min(down(Math.min(...lows), TEMP_STEP), TEMP_FLOOR);
  const ceiling = Math.max(up(Math.max(...highs), TEMP_STEP), TEMP_CEILING);
  const span = ceiling - floor || 1;
  const rain = Math.max(
    up(Math.max(...days.map((day) => day.precip_mm)), RAIN_STEP),
    RAIN_CEILING,
  );

  const left = GUTTER_LEFT + PAD;
  const right = WIDTH - GUTTER_RIGHT - PAD;
  const x = (index: number) =>
    days.length === 1
      ? (left + right) / 2
      : left + (index * (right - left)) / (days.length - 1);
  const y = (value: number) =>
    HEIGHT - PAD - ((value - floor) / span) * (HEIGHT - 2 * PAD);

  const path = (values: number[]) =>
    values
      .map(
        (value, index) => `${index === 0 ? "M" : "L"}${x(index)} ${y(value)}`,
      )
      .join(" ");

  return (
    <figure className="grid gap-1">
      <figcaption className="text-muted-foreground text-sm">
        {summarise(summary)}
      </figcaption>

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
            // The full height, not a third of it. A wet day and a very wet day were three
            // pixels apart at the bottom of the frame, which is a scale nobody can read.
            y={HEIGHT - PAD - (day.precip_mm / rain) * (HEIGHT - 2 * PAD)}
            width={4}
            height={(day.precip_mm / rain) * (HEIGHT - 2 * PAD)}
            className="fill-sky-400/50"
          />
        ))}
        {/* The scales. Three labels each: nothing between them has to be read precisely,
            and the table below carries every exact value anyway. */}
        {/* Each column of numbers is centred on its own axis, so the values sit under
            each other rather than ragged against the edge of the frame. */}
        {ticks(floor, ceiling, TEMP_STEP).map((value) => (
          <text
            key={`t${value}`}
            x={GUTTER_LEFT / 2}
            y={y(value) + 3}
            textAnchor="middle"
            className="fill-orange-600 text-[9px]"
          >
            {value}°
          </text>
        ))}
        {ticks(0, rain, RAIN_STEP).map((value) => (
          <text
            key={`r${value}`}
            x={WIDTH - GUTTER_RIGHT / 2}
            y={HEIGHT - PAD - (value / rain) * (HEIGHT - 2 * PAD) + 3}
            textAnchor="middle"
            className="fill-sky-600 text-[9px]"
          >
            {value}
          </text>
        ))}
        <text
          x={WIDTH - GUTTER_RIGHT / 2}
          y={9}
          textAnchor="middle"
          className="fill-sky-600 text-[8px]"
        >
          mm
        </text>

        {floor <= FROST_C && ceiling >= FROST_C ? (
          <line
            x1={GUTTER_LEFT}
            x2={WIDTH - GUTTER_RIGHT}
            y1={y(FROST_C)}
            y2={y(FROST_C)}
            className="stroke-muted-foreground/40"
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        ) : null}
        <path
          d={path(highs)}
          fill="none"
          className="stroke-orange-500"
          strokeWidth={1.5}
        />
        <path
          d={path(lows)}
          fill="none"
          className="stroke-blue-500"
          strokeWidth={1.5}
        />

        {/* The two days worth finding by eye. Both are named in the caption as well, since
            the chart is decorative and a mark nobody can read is not information. */}
        {captured >= 0 ? (
          <line
            x1={x(captured)}
            x2={x(captured)}
            y1={0}
            y2={HEIGHT}
            className="stroke-primary"
            strokeWidth={1.5}
          />
        ) : null}
        {today >= 0 && today !== captured ? (
          <line
            x1={x(today)}
            x2={x(today)}
            y1={0}
            y2={HEIGHT}
            className="stroke-muted-foreground/70"
            strokeDasharray="2 2"
            strokeWidth={1}
          />
        ) : null}
      </svg>

      <p className="text-muted-foreground text-xs">
        {/* Said in words as well as drawn, because the chart is decorative and a mark
            nobody can read is not information.

            The fallback carries more weight than it looks: every window stored before
            the capture day was included ends the day *before* the photograph, so those
            charts have no day to mark and would otherwise say nothing about what they
            cover. */}
        {captured >= 0
          ? `The solid line is ${asDate(days[captured]!.on)}, when this was photographed.`
          : `The three weeks up to ${asDate(days.at(-1)!.on)}, before this was photographed.`}
        {today >= 0 && today !== captured ? " The dashed line is today." : null}
      </p>

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

/** A date in the reader's own format, from the `YYYY-MM-DD` the series carries. */
function asDate(on: string): string {
  const when = new Date(`${on}T00:00:00`);
  return Number.isNaN(when.valueOf())
    ? on
    : when.toLocaleDateString(undefined, { day: "numeric", month: "long" });
}
