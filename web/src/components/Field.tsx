import { useId, type ReactNode } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * A labelled input, with its error attached to it.
 *
 * The label is bound by a generated id rather than by wrapping, and the error is announced
 * through `aria-describedby` — a message that only sits next to a field visually is a
 * message a screen reader reaches after the field it is about, if at all.
 */
export function Field({
  label,
  error,
  hint,
  ...props
}: {
  label: string;
  error?: string;
  hint?: ReactNode;
} & React.ComponentProps<typeof Input>) {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const described = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={described || undefined}
        {...props}
      />
      {hint ? (
        <p id={hintId} className="text-muted-foreground text-sm">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
