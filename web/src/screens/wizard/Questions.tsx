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
  // Seeded from the prefills. The run already believes these — a place read from the
  // photograph, the date it was taken — and they are the answer unless somebody changes
  // them, so they start in the fields rather than beside them.
  const [answers, setAnswers] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      questions
        .filter((question) => question.prefill)
        .map((question) => [question.key, question.prefill as string]),
    ),
  );

  // Which required questions were left empty when somebody tried to submit. Empty until
  // they do: marking a field wrong before anybody has attempted anything is telling them
  // off for not having finished yet.
  const [missing, setMissing] = useState<string[]>([]);
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
        // The application says what is wrong, in its own words, somewhere a screen reader
        // announces. A native validation bubble is none of those — and it silently swallows
        // the submit event, which is how this was found: the message below never appeared
        // because the handler never ran. `required` stays on the inputs, because assistive
        // technology reads it; only the browser's own enforcement is turned off.
        noValidate
        onSubmit={(event) => {
          event.preventDefault();

          // The form's half of this. The server checks too, because a form stops somebody
          // submitting by accident and stops nothing else — see `_require_answers`.
          const empty = questions
            .filter((question) => question.required)
            .filter((question) => !(answers[question.key] ?? "").trim())
            .map((question) => question.key);
          setMissing(empty);
          if (empty.length) return;

          // Only what was actually answered. An empty string is somebody who left a
          // question alone, and sending it as an answer is inventing one.
          // An empty answer is dropped, unless the field was prefilled — in which case
          // empty means somebody deliberately cleared what the run believed, and the
          // difference matters: absent means "never asked, keep what you had", and empty
          // means "forget it". Sending nothing for a cleared date would silently restore
          // the date it was cleared from.
          const prefilled = new Set(
            questions.filter((question) => question.prefill).map((q) => q.key),
          );
          onAnswer(
            Object.fromEntries(
              Object.entries(answers).filter(
                ([key, given]) => given !== "" || prefilled.has(key),
              ),
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
            invalid={missing.includes(question.key)}
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
