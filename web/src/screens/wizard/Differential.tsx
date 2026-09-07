import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import type { DiagnosisDetail, Source, TokenUsage } from "@/api/types";
import { Severity } from "@/components/Severity";
import { Verdict } from "@/components/Verdict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * What the agent thinks, in order, with what argues each way.
 *
 * **Not a verdict.** The leading candidate is often right and not always, and the tail of a
 * differential is measurably less stable than its head — showing one answer would present a
 * ranking as a fact. So every candidate is here, with its probability, the evidence on both
 * sides, and the quick check that would separate it from the others.
 */
export function Differential({ detail }: { detail: DiagnosisDetail }) {
  const { diagnosis } = detail;
  const heading = useRef<HTMLHeadingElement>(null);

  // The result replaces the reasoning panel in place, with no navigation. Without this,
  // somebody using a screen reader is left wherever the last step put them while the thing
  // they waited for is elsewhere on the page — the same reason the questions step takes
  // focus when it arrives.
  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <section aria-labelledby="differential" className="grid gap-4">
      <h2
        id="differential"
        ref={heading}
        tabIndex={-1}
        className="text-lg font-medium"
      >
        What this looks like
      </h2>

      {/* Above the reasoning, because which way the plant is going is the first thing
          somebody wants from a re-check and the reasoning is why. Renders nothing at all on
          a first diagnosis, which has nothing to compare against. */}
      <Verdict verdict={diagnosis.progress_verdict} />

      <p>{diagnosis.reasoning}</p>

      {/* **Rendered in the order the API returned, never re-sorted here** (`U22`). The
          `diagnose` node ranks the differential and `eval/` scores that ranking; a second
          sort on the client was a second opinion about which candidate leads, in the one
          place no measurement can see. The two rules agreed, so nothing was ever observed
          to move — which is exactly what made it worth removing rather than watching.

          Named, so that "the candidate is ranked here" is assertable as distinct from "the
          word appears on the page" — the consulted-material list below names disorders
          too. A list with a name is also easier to move between when navigating by
          landmark. */}
      <ol aria-label="Ranked candidates" className="grid gap-4">
        {diagnosis.candidates.map((candidate) => (
          <li key={candidate.disorder_id}>
            <Card>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-3">
                  <span>{candidate.name}</span>
                  <Severity severity={candidate.severity} />
                  <span className="text-muted-foreground text-sm font-normal">
                    {/* A proportion, in words as well as a number: "0.62" alone invites
                        being read as a certainty. */}
                    {Math.round(candidate.probability * 100)}% likely
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                {candidate.supporting_evidence.length ? (
                  <div>
                    <h3 className="font-medium">What points to it</h3>
                    <ul className="list-disc pl-5">
                      {candidate.supporting_evidence.map((evidence) => (
                        <li key={evidence}>{evidence}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {candidate.contradicting_evidence.length ? (
                  <div>
                    <h3 className="font-medium">What argues against it</h3>
                    <ul className="list-disc pl-5">
                      {candidate.contradicting_evidence.map((evidence) => (
                        <li key={evidence}>{evidence}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  /* Stated, not left as a gap (`U24`). The retired Streamlit view captioned
                     this case and the migration dropped it, so the one absence worth
                     calling out became indistinguishable from every other — a reader saw
                     a space where a line had said the question was asked and the answer
                     was none.

                     Deliberately asymmetric with "What points to it", which has no such
                     fallback and must not gain one: a candidate with nothing against it is
                     ordinary, and one with nothing *for* it is strange. Captioning that
                     would dress a defect up as a finding. */
                  <p className="text-muted-foreground">
                    Nothing observed argues against this.
                  </p>
                )}

                {candidate.distinguishing_test ? (
                  <div>
                    <h3 className="font-medium">How to tell</h3>
                    <p>{candidate.distinguishing_test}</p>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </li>
        ))}
      </ol>

      {/* Optional-chained although the contract requires the field. A client held open in
          a tab across a deployment can be reading a response shaped by the previous one,
          and losing the whole differential over a missing display field is the wrong
          trade — the same judgement `DiagnosisPage` makes about the activity panel, which
          deliberately does not branch on its own error. */}
      {diagnosis.sources?.length ? (
        <Consulted sources={diagnosis.sources} />
      ) : null}

      {detail.roadmap_steps.length ? (
        <section aria-labelledby="plan">
          <h2 id="plan" className="mb-2 text-lg font-medium">
            What to do about it
          </h2>
          <ol className="grid gap-2">
            {[...detail.roadmap_steps]
              .sort((a, b) => a.ordinal - b.ordinal)
              .map((step) => (
                <li key={step.id} className="text-sm">
                  <span className="font-medium">{step.action}</span> —{" "}
                  {step.rationale}
                </li>
              ))}
          </ol>
          <p className="text-muted-foreground mt-2 text-sm">
            You can tick these off on{" "}
            <Link to={`/plants/${diagnosis.plant_id}`}>
              the plant's own page
            </Link>
            .
          </p>
        </section>
      ) : null}

      <Spend
        cost={diagnosis.cost_usd ?? null}
        usage={diagnosis.token_usage ?? null}
      />
    </section>
  );
}

/**
 * Every passage the diagnosis was given, behind a disclosure.
 *
 * **A disclosure and not an open list.** The differential is the answer somebody came for,
 * and a real diagnosis consults eighteen passages — listing them above the treatment plan
 * would bury both. `<details>` rather than a button and state because it is the element
 * for exactly this, and it opens before any JavaScript has run.
 *
 * **Named and sectioned, never scored.** `M4` records that corpus cosine scores and Tavily
 * relevance scores land in one list after web escalation and are not comparable; the
 * retired Streamlit view labelled this list by source for that reason rather than printing
 * a number two passages could be wrongly compared on. Provenance is the useful distinction
 * anyway: a corpus section was written for this project, a web result was found.
 *
 * The count is on the summary so the size is known before opening — an expander hiding
 * three things and one hiding thirty invite different decisions.
 */
function Consulted({ sources }: { sources: Source[] }) {
  return (
    <details className="rounded-md border px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium">
        Reference material consulted ({sources.length})
      </summary>
      <ul className="mt-2 grid gap-1.5">
        {sources.map((source, index) => (
          // Index in the key on purpose: two sections of one document are two entries and
          // nothing here is a stable identifier, the list being a record of one run.
          <li
            key={`${source.name}-${source.section}-${index}`}
            className="text-sm"
          >
            <span className="font-medium">{source.name}</span>
            <span className="text-muted-foreground"> — {source.section}</span>
            <span className="text-muted-foreground ml-2 rounded border px-1.5 py-0.5 text-xs">
              {source.origin === "web" ? "Web" : "Knowledge base"}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/**
 * What the diagnosis spent.
 *
 * **Nothing at all when nothing was measured.** A failed run records no cost (`M18`), and
 * neither does any diagnosis made before this was kept — "$0.0000" would claim it ran and
 * was free, which is a different and false statement. The two figures are independent for
 * the same reason `core/cost.py` keeps a null cost rather than inventing a zero: the
 * provider reports usage and price separately, and either can be absent.
 *
 * Tokens beside the price, not instead of it: a price alone reads as a charge, where a
 * count and a price together read as a measurement. Four decimal places because a
 * diagnosis costs about two and a half cents and rounding to two would print "$0.03" for
 * everything.
 */
function Spend({
  cost,
  usage,
}: {
  cost: number | null;
  usage: TokenUsage | null;
}) {
  if (cost === null && usage === null) return null;

  const parts = [
    // `en-US` explicitly, not the viewer's locale. Every other word on this screen is
    // English, and a bare `toLocaleString()` groups by whatever locale the runtime happens
    // to carry — "12.946" on a German machine, which next to English copy reads as a
    // decimal point rather than a thousands separator. It also made this figure differ
    // between a developer's machine and CI.
    usage ? `${usage.total_tokens.toLocaleString("en-US")} tokens` : null,
    cost === null ? null : `$${cost.toFixed(4)}`,
  ].filter(Boolean);

  return <p className="text-muted-foreground text-xs">{parts.join(" · ")}</p>;
}
