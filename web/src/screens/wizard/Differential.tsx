import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import type { DiagnosisDetail } from "@/api/types";
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

  const ranked = [...diagnosis.candidates].sort(
    (a, b) => b.probability - a.probability,
  );

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

      <ol className="grid gap-4">
        {ranked.map((candidate) => (
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
                ) : null}

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
    </section>
  );
}
