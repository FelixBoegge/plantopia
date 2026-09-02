import type { Diagnosis } from "@/api/types";

/**
 * Which way a plant is going, compared with the diagnosis before it.
 *
 * **Never colour alone**, on the same reasoning as `Severity`: red and green are the two
 * hues roughly one man in twelve cannot reliably separate, and "is my plant getting better
 * or worse" is precisely the question you cannot afford to answer with hue. Every verdict
 * carries its words, and the colour only agrees with them.
 *
 * Absent on a first diagnosis, which has nothing to compare against, and on any re-check
 * made before the verdict was recorded. Both render nothing rather than a label saying
 * "unknown", which would put a row on screen that reports no fact.
 */
const LABELS: Record<string, { text: string; className: string }> = {
  improving: {
    text: "Improving since the last diagnosis",
    className:
      "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  },
  static: {
    text: "About the same as the last diagnosis",
    className: "bg-muted text-muted-foreground",
  },
  worsening: {
    text: "Worse than the last diagnosis",
    className:
      "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  },
  new_problem: {
    text: "A different problem from last time",
    className: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-100",
  },
};

export function Verdict({
  verdict,
}: {
  verdict: Diagnosis["progress_verdict"];
}) {
  if (!verdict) return null;
  const shown = LABELS[verdict];
  // An unrecognised value renders nothing rather than its own identifier. A verdict the
  // server grew and this file has not learned about is not something to show somebody.
  if (!shown) return null;

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${shown.className}`}
    >
      {shown.text}
    </span>
  );
}
