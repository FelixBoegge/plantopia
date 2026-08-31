import { Link } from "react-router-dom";

import type { Diagnosis, Message, Observation, RoadmapStep } from "@/api/types";
import { Photo } from "@/components/Photo";
import { Weather } from "@/screens/plants/Weather";
import { seriesOf, timelineOf, type TimelineEvent } from "@/screens/plants/history";

/**
 * What has happened to this plant, newest first.
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
        What has happened
      </h2>

      {events.length === 0 ? (
        <p className="text-muted-foreground">
          Nothing has happened to this plant yet. Once you run a check, what you saw and what
          Plantopia made of it will appear here.
        </p>
      ) : (
        <ol className="grid gap-4">
          {events.map((event) => (
            <li key={`${event.kind}:${event.id}`} className="border-l-2 pl-4">
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

  return (
    <article className="grid gap-2">
      <Heading
        label={observation.kind === "recheck" ? "Photographed again" : "First photographed"}
        at={event.at}
        // Said only where it is true. An upload date presented as a capture date would be
        // the timeline claiming something the photograph never declared.
        note={event.dated === "uploaded" ? "date the photograph was uploaded" : undefined}
      />

      <div className="flex flex-wrap items-start gap-3">
        {observation.photo_refs.map((ref) => (
          // Through `Photo`, which fetches with the bearer token and hands back an object
          // URL. A bare `src` cannot send an Authorization header and would render broken.
          <Photo
            key={ref}
            photoKey={ref}
            alt="This plant, as photographed"
            className="h-20 w-20 rounded-md object-cover"
          />
        ))}
      </div>

      {observation.user_notes ? <p>{observation.user_notes}</p> : null}

      {series ? <Weather summary={series} /> : null}
    </article>
  );
}

function DiagnosisEvent({ event }: { event: Extract<TimelineEvent, { kind: "diagnosis" }> }) {
  const { diagnosis } = event;
  const leading = diagnosis.candidates[0];

  return (
    <article className="grid gap-1">
      <Heading label="Diagnosed" at={event.at} />
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
      <Link to={`/diagnoses/${diagnosis.id}`} className="text-sm underline underline-offset-4">
        See this diagnosis
      </Link>
    </article>
  );
}

function StepEvent({ event }: { event: Extract<TimelineEvent, { kind: "step" }> }) {
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

function EscalationEvent({ event }: { event: Extract<TimelineEvent, { kind: "escalation" }> }) {
  return (
    <article className="grid gap-1">
      <Heading label="Flagged for a fresh look" at={event.at} />
      {event.reason ? <p>{event.reason}</p> : null}
    </article>
  );
}

function Heading({ label, at, note }: { label: string; at: string; note?: string }) {
  return (
    <p className="flex flex-wrap items-baseline gap-2">
      <span className="font-medium">{label}</span>
      <time dateTime={at} className="text-muted-foreground text-sm">
        {readableDate(at)}
      </time>
      {note ? <span className="text-muted-foreground text-sm">({note})</span> : null}
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
