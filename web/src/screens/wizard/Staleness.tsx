import { Notice } from "@/components/Notice";

/** The answer key the capture date is under, as `agent/nodes/context.py` names it. */
export const CAPTURE_KEY = "captured_at";

/**
 * How old the photograph is, in days, or `null` when the date is missing or unreadable.
 *
 * Judged by the date in the field rather than by the one the camera recorded. The field is
 * prefilled from the metadata and the owner may correct it — somebody who knows the camera's
 * clock is wrong, or who is uploading a scan — and a warning that ignored the correction
 * would be arguing with them about a fact they just supplied.
 */
export function ageInDays(captured: string, today: Date): number | null {
  const taken = new Date(`${captured}T00:00:00`);
  if (Number.isNaN(taken.getTime())) return null;

  const midnight = new Date(today);
  midnight.setHours(0, 0, 0, 0);
  return Math.round((midnight.getTime() - taken.getTime()) / 86_400_000);
}

/**
 * Said when the photograph is old enough to mislead.
 *
 * A plant changes. A photograph three weeks old shows a plant that no longer exists, and a
 * diagnosis of it is a diagnosis of the past presented as advice about the present —
 * confident, detailed, and about something that has since recovered or got considerably
 * worse.
 *
 * Said here, at the pause, because this is the last moment where somebody can still go and
 * photograph the plant again before paying for a diagnosis. It is a caution rather than a
 * refusal: somebody whose plant died last week and who has only last week's photograph is
 * exactly who needs an answer, and the run carries on either way.
 */
export function Staleness({
  captured,
  threshold,
  today = new Date(),
}: {
  captured: string | undefined;
  threshold: number | null;
  today?: Date;
}) {
  if (!captured || threshold === null) return null;

  const age = ageInDays(captured, today);
  // A date in the future is somebody mid-keystroke or a camera clock set wrong. Neither is
  // a stale photograph, and neither wants a warning about one.
  if (age === null || age <= threshold) return null;

  return (
    <Notice tone="caution">
      This photograph is {age} days old. A plant can change a great deal in that time, so
      the diagnosis will be less reliable. If you can, upload one taken today.
    </Notice>
  );
}
