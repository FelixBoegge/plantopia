import { useEffect, useRef, useState } from "react";

import { readable } from "@/api/problems";
import type { Question as Asked, SpeciesCandidate } from "@/api/types";
import { Notice } from "@/components/Notice";
import { Identification } from "@/screens/wizard/Identification";
import { IdentifiedAs } from "@/screens/wizard/IdentifiedAs";
import { Question } from "@/screens/wizard/Question";
import { CAPTURE_KEY, Staleness } from "@/screens/wizard/Staleness";
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
  staleAfterDays,
  onAnswer,
  busy,
  locked,
  failure,
}: {
  questions: Asked[];
  /**
   * Every candidate the run considered — always at least one once the pause has
   * actually arrived. `null` only means the pause has not happened yet; whether there
   * is a real choice to make is a question of length, not presence, answered below.
   */
  identification: SpeciesCandidate[] | null;
  /** How old a photograph may be before it is worth saying so. */
  staleAfterDays: number | null;
  onAnswer: (
    answers: Record<string, string>,
    species: SpeciesCandidate | null,
  ) => void;
  /** A send is in flight. */
  busy: boolean;
  /**
   * The answers are with the run and cannot be changed.
   *
   * Distinct from `busy`, which is the moment of sending. This is everything after it: the
   * pause is over, the agent is reasoning from these, and an editable field would be an
   * invitation to change an answer that has already been acted on.
   */
  locked: boolean;
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

      {/*
        Follows the date field rather than the metadata, so correcting the date corrects
        the verdict. Above the form because it is a reason to stop and take another
        photograph, and something that only appeared beside the submit button would be read
        after the decision had already been made.
      */}
      <Staleness captured={answers[CAPTURE_KEY]} threshold={staleAfterDays} />

      {/*
        One `fieldset` over both the species choice and the questions, because the species
        radios sit outside the form — they are answered by the same click and have to lock
        with it. `disabled` on a fieldset disables every control descending from it,
        including those in the nested form, so this is one mechanism rather than a prop
        threaded through two components and a third that renders each input.
      */}
      <fieldset disabled={locked} className="grid min-w-0 gap-4 border-0 p-0">
        {identification && species ? (
          identification.length > 1 ? (
            <Identification
              candidates={identification}
              chosen={species}
              onChoose={setSpecies}
            />
          ) : (
            <IdentifiedAs candidate={species} />
          )
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
              questions
                .filter((question) => question.prefill)
                .map((q) => q.key),
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
            {/* Gone rather than disabled once sent. A greyed-out "Carry on" reads as
                something that will become available again, and this one never will —
                the run has the answers and the next thing to happen is the result. */}
            {locked ? (
              <p className="text-muted-foreground text-sm" role="status">
                Answers sent. Plantopia is working on them.
              </p>
            ) : (
              <Button type="submit" disabled={busy}>
                {busy ? "Sending…" : "Carry on"}
              </Button>
            )}
          </div>
        </form>
      </fieldset>
    </section>
  );
}
