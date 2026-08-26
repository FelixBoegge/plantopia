import { useEffect, useRef, useState } from "react";

import { readable } from "@/api/problems";
import type { Question as Asked, SpeciesCandidate } from "@/api/types";
import { Notice } from "@/components/Notice";
import { Identification } from "@/screens/wizard/Identification";
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
  identification,
  onAnswer,
  busy,
  failure,
}: {
  questions: Asked[];
  /** The identifications to choose between, or `null` when they agreed. */
  identification: SpeciesCandidate[] | null;
  onAnswer: (answers: Record<string, string>, species: SpeciesCandidate | null) => void;
  busy: boolean;
  failure: unknown;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // Starts on the leading candidate, which the run has already put first. Preselected
  // rather than empty because there is no such thing as no species here — leaving it alone
  // means proceeding on the leader, and an empty radiogroup would suggest otherwise.
  const [species, setSpecies] = useState<SpeciesCandidate | null>(
    identification?.[0] ?? null,
  );
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

      {identification && species ? (
        <Identification
          candidates={identification}
          chosen={species}
          onChoose={setSpecies}
        />
      ) : null}

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
            // Only when there was something to choose between *and* it differs from what
            // the run would have done anyway. Sending back the leader unchanged would
            // record that somebody confirmed it, which is a different fact from nobody
            // having disagreed.
            species && species !== identification?.[0] ? species : null,
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
