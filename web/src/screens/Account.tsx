import {
  allowance,
  useAccount,
  useFacts,
  useForgetFact,
} from "@/api/hooks/account";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * What Plantopia knows about somebody, and what they agreed to.
 *
 * A system that infers durable facts about a person and offers no way to see or remove them
 * is one they cannot correct. This screen is the answer to that, and the reason the privacy
 * notice at registration can promise it.
 */
export function Account() {
  const { data: account, error } = useAccount();
  const left = allowance(account);

  return (
    <div className="grid max-w-2xl gap-8">
      <h1 className="text-2xl font-semibold">Your account</h1>

      {error ? <Notice tone="failure">{readable(error)}</Notice> : null}

      {account ? (
        <Card>
          <CardHeader>
            <CardTitle>{account.email}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <p>
              You agreed to the privacy notice of {account.consent_version} on{" "}
              {new Date(account.consent_at).toLocaleDateString()}.
            </p>
            {left ? (
              <p>
                {left.used} of {left.limit} checks used this month. It resets on{" "}
                {left.resetsAt.toLocaleDateString()}.
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {left?.exhausted ? (
        <Notice title="No checks left this month">
          You have used all {left.limit}. You can start another after{" "}
          {left.resetsAt.toLocaleDateString()}.
        </Notice>
      ) : null}

      <LearnedFacts />
    </div>
  );
}

function LearnedFacts() {
  const { data: facts, isPending, error } = useFacts();
  const forget = useForgetFact();

  return (
    <section aria-labelledby="learned" className="grid gap-3">
      <h2 id="learned" className="text-lg font-medium">
        What Plantopia has learned about you
      </h2>
      <p className="text-muted-foreground text-sm">
        These are used to answer your questions. Remove any of them and they
        stop being.
      </p>

      {isPending ? <p role="status">Loading…</p> : null}
      {error ? <Notice tone="failure">{readable(error)}</Notice> : null}
      {forget.error ? (
        <Notice tone="failure">{readable(forget.error)}</Notice>
      ) : null}

      {facts?.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Nothing yet. Facts are picked up from what you say in conversations.
        </p>
      ) : null}

      {facts?.length ? (
        <ul className="grid gap-2">
          {facts.map((fact) => (
            <li
              key={fact.fact}
              className="flex items-start justify-between gap-4 rounded-md border p-3"
            >
              <div className="grid gap-1 text-sm">
                <span>{fact.fact}</span>
                <span className="text-muted-foreground text-xs">
                  {fact.source === "stated"
                    ? "You told it this"
                    : "It worked this out"}{" "}
                  · first noticed{" "}
                  {new Date(fact.first_seen).toLocaleDateString()} ·{" "}
                  {/* Confidence in words as well as a number: "0.62" alone invites being
                      read as a certainty. */}
                  {fact.confidence >= 0.8
                    ? "fairly sure"
                    : fact.confidence >= 0.5
                      ? "moderately sure"
                      : "not very sure"}
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => forget.mutate(fact.fact)}
                disabled={forget.isPending}
              >
                Forget this
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
