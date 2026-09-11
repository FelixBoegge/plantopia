/**
 * How urgently somebody needs to do something.
 *
 * **Never colour alone.** Roughly one man in twelve cannot reliably separate the red and
 * green a severity badge uses, and a diagnosis whose seriousness is carried only by hue is
 * one they cannot read. Every badge carries its words.
 *
 * One component, used everywhere a severity appears, so that this is a property of a thing
 * with a test rather than a rule each screen has to remember.
 *
 * **The dark palette is light, not dark.** The obvious dark-mode badge is a very dark tint
 * of its hue — `amber-950`, `red-950` — and on this theme's near-black page those read as
 * two slightly different dark rectangles: neither legible at a glance nor distinguishable
 * from each other, which is the whole job. So dark mode uses a *brighter* fill with dark
 * ink on it, and the three levels step up in weight — neutral, amber, red — so urgency is
 * carried by how much the badge asserts itself and not by hue alone.
 */

const LABELS: Record<string, { text: string; className: string }> = {
  monitor: {
    text: "Keep an eye on it",
    className: "bg-muted text-muted-foreground",
  },
  act_this_week: {
    text: "Act this week",
    className:
      "bg-amber-200 text-amber-950 dark:bg-amber-300 dark:text-amber-950",
  },
  act_today: {
    text: "Act today",
    className: "bg-red-200 text-red-950 dark:bg-red-400 dark:text-red-950",
  },
};

const UNKNOWN = {
  text: "Unrated",
  className: "bg-muted text-muted-foreground",
};

// Green, and its own case rather than a fourth row in `LABELS`: severity ranks how
// urgently something needs doing, and a healthy plant has nothing to do anything about
// — a healthy differential carries no candidates at all (the schema forbids it), so
// there is no severity to look up in the first place. Checked first for exactly that
// reason: `severity` is never present alongside it.
const HEALTHY = {
  text: "Healthy",
  className:
    "bg-green-200 text-green-950 dark:bg-green-300 dark:text-green-950",
};

function badge(text: string, className: string, extra?: string) {
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

export function Severity({
  severity,
  healthy,
  className: extra,
}: {
  /** Optional: a caller showing only a healthy plant has none to give. */
  severity?: string | null;
  /** Whether the plant was found healthy. Takes precedence over `severity`, which a
      healthy diagnosis never carries one of anyway. */
  healthy?: boolean;
  /** Appended, so a caller can size it. Everything else about it stays fixed. */
  className?: string;
}) {
  if (healthy) return badge(HEALTHY.text, HEALTHY.className, extra);
  if (!severity) return null;
  // An unknown value still renders words. Falling back to the raw value would put
  // `act_this_week` on a screen, which is a database value, not a sentence.
  const { text, className } = LABELS[severity] ?? UNKNOWN;
  return badge(text, className, extra);
}

/** The words alone, for places that are already inside a sentence. */
export function severityText(
  severity: string | null | undefined,
): string | null {
  if (!severity) return null;
  return (LABELS[severity] ?? UNKNOWN).text;
}
