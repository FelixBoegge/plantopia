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
 * **A choice starts unanswered, and can stay that way.** An unanswered boolean recorded as
 * "no" is a limitation this project already carried once (U4): it puts words in somebody's
 * mouth, and the graph cannot tell the difference between a considered "no" and a shrug.
 * Only keys with a value are sent.
 */
export function Question({
  question,
  value,
  onChange,
}: {
  question: Asked;
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const choices =
    question.kind === "boolean" ? ["Yes", "No"] : question.options;

  if (question.kind === "text") {
    return (
      <div className="grid gap-2">
        <Label htmlFor={id}>{question.text}</Label>
        <Input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{question.text}</Label>
      <select
        id={id}
        value={value}
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
    </div>
  );
}
