import { useState } from "react";
import { Link } from "react-router-dom";

import type { Diagnosis, Message, Observation, RoadmapStep } from "@/api/types";
import { Photo } from "@/components/Photo";
import { PhotoViewer } from "@/components/PhotoViewer";
import { Verdict } from "@/components/Verdict";
import { Weather } from "@/screens/plants/Weather";
import {
  seriesOf,
  timelineOf,
  type TimelineEvent,
} from "@/screens/plants/history";

/**
 * This plant's history, newest first.
 *
 * The question an owner has after the second or third diagnosis is whether the plant is
 * getting better, and that question is about sequence: what was seen, what it was judged to
 * be, what was done, what the weather was doing. Four separate lists make the reader do the
 * interleaving; this does it for them.
 *
 * Everything here was already fetched by the page. Nothing is drawn that the data does not
 * carry — an observation from before capture dates existed shows what it has and says
 * nothing about what it does not, rather than showing an epoch date or a zero.
 */
export function Timeline({
  observations,
  diagnoses,
  steps,
  messages,
}: {
  observations: Observation[];
  diagnoses: Diagnosis[];
  steps: RoadmapStep[];
  /** Optional: the transcript is a second request and the timeline does not wait for it. */
  messages?: Message[];
}) {
  const events = timelineOf({ observations, diagnoses, steps, messages });

  return (
    <section aria-labelledby="history">
      <h2 id="history" className="mb-3 text-lg font-medium">
        Plant history
      </h2>

      {/* A rule between entries, not only space. An entry can run long — photographs, a
          weather chart, a finding — and by the time somebody reaches the bottom of one it is
          not obvious where the next begins. `divide-y` draws the line only between them,
          never above the first or below the last. */}
      {events.length === 0 ? (
        <p className="text-muted-foreground">
          Nothing has happened to this plant yet. Once you run a diagnosis, what
          you saw and what Plantopia made of it will appear here.
        </p>
      ) : (
        <ol className="divide-border grid divide-y">
          {events.map((event, index) => (
            <li
              key={`${event.kind}:${event.id}`}
              className="relative border-l-2 py-4 pl-4 first:pt-0 last:pb-0"
            >
              {/* Counted from the bottom, so the first thing that happened is 1 and an
                  entry's number never changes when a newer one appears above it. The list
                  itself is newest first, which is the order the question a history answers
                  — is this getting better? — is asked in. */}
              <span
                aria-hidden="true"
                className="bg-muted text-muted-foreground absolute -left-3 flex size-5 items-center justify-center rounded-full text-xs font-medium"
              >
                {events.length - index}
              </span>
              <Event event={event} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Event({ event }: { event: TimelineEvent }) {
  switch (event.kind) {
    case "observation":
      return <ObservationEvent event={event} />;
    case "diagnosis":
      return <DiagnosisEvent event={event} />;
    case "step":
      return <StepEvent event={event} />;
    case "escalation":
      return <EscalationEvent event={event} />;
  }
}

function ObservationEvent({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "observation" }>;
}) {
  const { observation } = event;
  const series = seriesOf(observation);
  const [enlarged, setEnlarged] = useState<string | null>(null);

  return (
    <article className="grid gap-2">
      {/* The finding first, then what it was made from. Somebody scanning a history is
          asking what happened; the photographs are the evidence for the answer rather than
          the answer itself. An observation with no diagnosis leads with its own heading,
          because then the photographs are all there is. */}
      {event.diagnosis ? (
        <Finding diagnosis={event.diagnosis} at={event.at} />
      ) : (
        <Heading
          label={
            observation.kind === "recheck"
              ? "Photographed again"
              : "First photographed"
          }
          at={event.photographedAt}
          note={
            event.dated === "uploaded"
              ? "date the photograph was uploaded"
              : undefined
          }
        />
      )}

      {event.diagnosis ? (
        <p className="text-muted-foreground text-sm">
          {/* Both dates, because they differ whenever an old photograph is diagnosed
              today — which is exactly when a reader needs telling which is which.

              A real <time>, not a formatted string dropped into the paragraph: this is
              the one place the earlier version of this lost the machine-readable date the
              rest of the file keeps deliberately, because the visible text is locale-
              formatted and nothing should be asserted against it. */}
          {observation.kind === "recheck"
            ? "Photographed again"
            : "First photographed"}{" "}
          on{" "}
          <time dateTime={event.photographedAt}>
            {readableDate(event.photographedAt)}
          </time>
          {event.dated === "uploaded"
            ? " (date the photograph was uploaded)"
            : null}
          .
        </p>
      ) : null}

      <div className="flex flex-wrap items-start gap-3">
        {observation.photo_refs.map((ref, index) => (
          // A button, not an image with a click handler: this is a control, and making it
          // one is what gives it the keyboard, the focus ring and a name for free.
          //
          // Inside it, `Photo` — which fetches with the bearer token and hands back an
          // object URL. A bare `src` cannot send an Authorization header and would render
          // broken.
          <button
            key={ref}
            type="button"
            onClick={() => setEnlarged(ref)}
            aria-label={`Enlarge photograph ${index + 1}`}
            className="focus-visible:outline-ring hover:border-primary/60 rounded-md border border-transparent transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <Photo
              photoKey={ref}
              alt="This plant, as photographed"
              className="h-20 w-20 rounded-md object-cover"
            />
          </button>
        ))}
      </div>

      {enlarged ? (
        <PhotoViewer photoKey={enlarged} onClose={() => setEnlarged(null)} />
      ) : null}

      {observation.user_notes ? <p>{observation.user_notes}</p> : null}

      {series ? (
        <Weather summary={series} capturedOn={observation.captured_at} />
      ) : null}
    </article>
  );
}

function DiagnosisEvent({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "diagnosis" }>;
}) {
  // Only reached by a diagnosis whose observation is missing from the list. The ordinary
  // case is drawn inside the observation above.
  return (
    <article className="grid gap-1">
      <Finding diagnosis={event.diagnosis} at={event.at} />
    </article>
  );
}

function Finding({ diagnosis, at }: { diagnosis: Diagnosis; at: string }) {
  const leading = diagnosis.candidates[0];

  return (
    <>
      <Heading label="Diagnosed" at={at} />
      <Verdict verdict={diagnosis.progress_verdict} />
      <p>
        {diagnosis.is_healthy
          ? "Nothing wrong was found."
          : (leading?.name ?? "No candidate was produced.")}
      </p>
      {/*
        Not "See the full differential" — that is the wording the current-verdict section
        above already uses, and for the latest diagnosis both links point at the same page.
        Two identically-named links to one destination is a thing a screen reader reads
        twice and a person has to disambiguate by position.
      */}
      <Link
        to={`/diagnoses/${diagnosis.id}`}
        className="text-sm underline underline-offset-4"
      >
        See this diagnosis
      </Link>
    </>
  );
}

function StepEvent({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "step" }>;
}) {
  const { step } = event;
  // Only settled steps reach the timeline, so this is "done" or "skipped" and never
  // "to do" — the plan itself lives in <Roadmap>, where a pending step can be ticked.
  const label = step.status === "skipped" ? "Skipped" : "Done";

  return (
    <article className="grid gap-1">
      <Heading label={label} at={event.at} />
      <p>{step.action}</p>
    </article>
  );
}

function EscalationEvent({
  event,
}: {
  event: Extract<TimelineEvent, { kind: "escalation" }>;
}) {
  return (
    <article className="grid gap-1">
      <Heading label="Flagged for a fresh look" at={event.at} />
      {event.reason ? <p>{event.reason}</p> : null}
    </article>
  );
}

function Heading({
  label,
  at,
  note,
}: {
  label: string;
  at: string;
  note?: string;
}) {
  return (
    <p className="flex flex-wrap items-baseline gap-2">
      <span className="font-medium">{label}</span>
      <time dateTime={at} className="text-muted-foreground text-sm">
        {readableDate(at)}
      </time>
      {note ? (
        <span className="text-muted-foreground text-sm">({note})</span>
      ) : null}
    </p>
  );
}

/** A date somebody reads, from an instant the API sends. */
export function readableDate(at: string): string {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) return at;
  return when.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}
