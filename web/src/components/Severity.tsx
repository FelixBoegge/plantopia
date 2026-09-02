/**
 * How urgently somebody needs to do something.
 *
 * **Never colour alone.** Roughly one man in twelve cannot reliably separate the red and
 * green a severity badge uses, and a diagnosis whose seriousness is carried only by hue is
 * one they cannot read. Every badge carries its words.
 *
 * One component, used everywhere a severity appears, so that this is a property of a thing
 * with a test rather than a rule each screen has to remember.
 */

const LABELS: Record<string, { text: string; className: string }> = {
  monitor: {
    text: "Keep an eye on it",
    className: "bg-muted text-muted-foreground",
  },
  act_this_week: {
    text: "Act this week",
    className:
      "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  },
  act_today: {
    text: "Act today",
    className: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-100",
  },
};

const UNKNOWN = {
  text: "Unrated",
  className: "bg-muted text-muted-foreground",
};

export function Severity({
  severity,
  className: extra,
}: {
  severity: string | null | undefined;
  /** Appended, so a caller can size it. Everything else about it stays fixed. */
  className?: string;
}) {
  if (!severity) return null;
  // An unknown value still renders words. Falling back to the raw value would put
  // `act_this_week` on a screen, which is a database value, not a sentence.
  const { text, className } = LABELS[severity] ?? UNKNOWN;

  return (
    <span
      // `w-fit` because `inline-flex` is not enough on its own: as a grid item this
      // stretches to its column, which put a pill the width of the page around two words.
      className={`inline-flex w-fit shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${className} ${extra ?? ""}`}
    >
      {text}
    </span>
  );
}

/** The words alone, for places that are already inside a sentence. */
export function severityText(
  severity: string | null | undefined,
): string | null {
  if (!severity) return null;
  return (LABELS[severity] ?? UNKNOWN).text;
}
