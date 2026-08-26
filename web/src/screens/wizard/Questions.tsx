import { useEffect, useRef, useState } from "react";

import { readable } from "@/api/problems";
import type { Question as Asked } from "@/api/types";
import { Notice } from "@/components/Notice";
import { Question } from "@/screens/wizard/Question";
import { Button } from "@/components/ui/button";

/**
 * What the agent needs to know before it can go on.
 *
 * Answered in place. The pause is the middle of the run, not the end of it, and sending
 * somebody elsewhere and back would make every diagnosis feel like two.
 *
 * Focus moves here when the questions appear: this is the one moment in the run where the
 * person is expected to do something, and somebody using a keyboard would otherwise have to
 * hunt for where.
 */
export function Questions({
  questions,
  onAnswer,
  busy,
  failure,
}: {
  questions: Asked[];
  onAnswer: (answers: Record<string, string>) => void;
  busy: boolean;
  failure: unknown;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <section aria-labelledby="questions" className="grid max-w-xl gap-4">
      <h2
        id="questions"
        ref={heading}
        tabIndex={-1}
        className="text-lg font-medium"
      >
        A couple of questions
      </h2>

      {failure ? <Notice tone="failure">{readable(failure)}</Notice> : null}

      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          // Only what was actually answered. An empty string is somebody who left a
          // question alone, and sending it as an answer is inventing one.
          onAnswer(
            Object.fromEntries(
              Object.entries(answers).filter(([, given]) => given !== ""),
            ),
          );
        }}
      >
        {questions.map((question) => (
          <Question
            key={question.key}
            question={question}
            value={answers[question.key] ?? ""}
            onChange={(given) =>
              setAnswers((so_far) => ({ ...so_far, [question.key]: given }))
            }
          />
        ))}
        <div>
          <Button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Carry on"}
          </Button>
        </div>
      </form>
    </section>
  );
}
