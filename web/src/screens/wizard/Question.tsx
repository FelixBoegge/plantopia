import { useId } from "react";

import type { Question as Asked } from "@/api/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * One clarifying question, rendered as the kind of thing it is.
 *
 * A question with four fixed options is not a text box. It was one, for a while: the client
 * type omitted `kind` entirely, so every question — including "does the pot have drainage
 * holes", whose four answers the graph reasons over — arrived as free text somebody had to
 * guess the wording of.
 *
 * **A prefilled answer is in the field, not beside it.** Where the run already believes
 * something — a place read from the photograph, the date it was taken — that belief is the
 * answer, and it is used unless somebody says otherwise. A suggestion sitting next to an
 * empty box would ask the common case to do work; this asks only the uncommon one.
 *
 * **A choice starts unanswered, and can stay that way.** An unanswered boolean recorded as
 * "no" is a limitation this project already carried once (U4): it puts words in somebody's
 * mouth, and the graph cannot tell a considered "no" from a shrug. Only keys with a value
 * are sent, and only `required` questions refuse to be left alone.
 */
/**
 * Open the month view rather than putting a caret in the date segments.
 *
 * A date input's default click behaviour is to select whichever of day, month or year was
 * clicked, so changing a prefilled date meant typing over it. The calendar was always there
 * — with the current value already selected — behind an icon narrow enough that most people
 * never find it. This makes the whole field that icon.
 *
 * Typing still works: this opens the picker, it does not take the keyboard away.
 *
 * Guarded twice over. `showPicker` does not exist in older browsers or in jsdom, and where
 * it does exist it throws if the browser decides the call was not provoked by a person. A
 * date somebody cannot type because opening a calendar failed would be a worse field than
 * the one this replaces.
 */
function openTheCalendar(event: React.MouseEvent<HTMLInputElement>): void {
  const field = event.currentTarget;
  if (typeof field.showPicker !== "function") return;
  try {
    field.showPicker();
  } catch {
    // Left to the caret and the keyboard, which is where it was before.
  }
}

export function Question({
  question,
  value,
  onChange,
  invalid,
}: {
  question: Asked;
  value: string;
  onChange: (value: string) => void;
  /** Required, empty, and somebody tried to submit. */
  invalid?: boolean;
}) {
  const id = useId();
  const noteId = `${id}-note`;
  const errorId = `${id}-error`;
  const described =
    [question.prefill_note ? noteId : null, invalid ? errorId : null]
      .filter(Boolean)
      .join(" ") || undefined;

  const choices =
    question.kind === "boolean" ? ["Yes", "No"] : question.options;

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>
        {question.text}
        {question.required ? (
          <span className="text-muted-foreground ml-1 text-sm font-normal">
            {/* Said in words. An asterisk is a convention somebody has to already know,
                and it reads as nothing at all to a screen reader. */}
            (needed)
          </span>
        ) : null}
      </Label>

      {question.kind === "text" || question.kind === "date" ? (
        <Input
          id={id}
          type={question.kind === "date" ? "date" : "text"}
          value={value}
          required={question.required}
          aria-invalid={invalid || undefined}
          aria-describedby={described}
          onChange={(event) => onChange(event.target.value)}
          onClick={
            question.kind === "date" ? openTheCalendar : undefined
          }
        />
      ) : (
        <select
          id={id}
          value={value}
          required={question.required}
          aria-invalid={invalid || undefined}
          aria-describedby={described}
          onChange={(event) => onChange(event.target.value)}
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
        >
          <option value="">Not sure</option>
          {choices.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )}

      {question.prefill_note ? (
        <p id={noteId} className="text-muted-foreground text-sm">
          {/* Where the answer in the field came from — and, where the source's terms ask
              for it, the credit. Tied to the datum rather than to the page, so a screen
              showing one cannot omit the other. */}
          {question.prefill_note}
        </p>
      ) : null}

      {invalid ? (
        <p id={errorId} role="alert" className="text-destructive text-sm">
          This one is needed before the diagnosis can go on.
        </p>
      ) : null}
    </div>
  );
}
