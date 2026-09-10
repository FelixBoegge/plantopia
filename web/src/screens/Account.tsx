import { useState } from "react";

import {
  allowance,
  useAccount,
  useChangePassword,
  useDeleteAccount,
  useExport,
  useFacts,
  useForgetFact,
} from "@/api/hooks/account";
import type { TotalSpend } from "@/api/types";
import { useAuth } from "@/auth/AuthProvider";
import { Field } from "@/components/Field";
import { fieldMessages, readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { ShowPasswords } from "@/components/ShowPasswords";
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
                {left.used} of {left.limit} diagnoses used this month. It resets
                on {left.resetsAt.toLocaleDateString()}.
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {left?.exhausted ? (
        <Notice title="No diagnoses left this month">
          You have used all {left.limit}. You can start another after{" "}
          {left.resetsAt.toLocaleDateString()}.
        </Notice>
      ) : null}

      <LearnedFacts />

      {account ? <SpendSummary spend={account.total_spend} /> : null}

      <YourData />

      <ChangePassword />

      <DeleteAccount />
    </div>
  );
}

/** The phrase somebody types to confirm. Must match `services/erasure.CONFIRMATION`. */
const CONFIRMATION = "delete my account";

function YourData() {
  const take = useExport();

  return (
    <section aria-labelledby="your-data" className="border-t pt-6">
      <h2 id="your-data" className="mb-3 text-lg font-medium">
        Your data
      </h2>
      <p className="text-muted-foreground mb-3">
        Everything Plantopia holds about you — your plants, what it diagnosed,
        what you told it, and the photographs you uploaded — as one file you can
        keep.
      </p>

      {take.isError ? (
        <Notice tone="failure">{readable(take.error)}</Notice>
      ) : null}

      <Button
        variant="outline"
        onClick={() => take.mutate()}
        disabled={take.isPending}
      >
        {take.isPending ? "Preparing…" : "Download my data"}
      </Button>
    </section>
  );
}

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showing, setShowing] = useState(false);
  const [mismatch, setMismatch] = useState(false);
  const [done, setDone] = useState(false);
  const change = useChangePassword();
  const named = fieldMessages(change.error);

  return (
    <section aria-labelledby="change-password" className="border-t pt-6">
      <h2 id="change-password" className="mb-3 text-lg font-medium">
        Change your password
      </h2>

      <p className="text-muted-foreground mb-3">
        {/* Said here so nobody has to discover it by being signed out of their phone. */}
        Your current password proves this is you. Every other device is signed
        out; this one stays.
      </p>

      {done ? (
        <Notice title="Done">Your password has been changed.</Notice>
      ) : null}

      {/* Only what the server did not pin to a field. */}
      {change.error && Object.keys(named).length === 0 ? (
        <Notice tone="failure">{readable(change.error)}</Notice>
      ) : null}

      <form
        className="mt-3 grid max-w-md gap-4"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          // Checked here and nowhere else: the confirmation exists to catch a typo in a
          // box nobody can read back, which is a question about this screen rather than
          // about the account. Sending it would give the server a second copy of the same
          // mistake to compare against itself.
          setMismatch(next !== confirm);
          if (next !== confirm) return;
          setDone(false);
          change.mutate(
            { current_password: current, new_password: next },
            {
              onSuccess: () => {
                setDone(true);
                setCurrent("");
                setNext("");
                setConfirm("");
              },
            },
          );
        }}
      >
        <Field
          label="Current password"
          type={showing ? "text" : "password"}
          autoComplete="current-password"
          required
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          error={named.current_password}
        />
        <Field
          label="New password"
          type={showing ? "text" : "password"}
          autoComplete="new-password"
          required
          value={next}
          onChange={(event) => setNext(event.target.value)}
          hint="At least 12 characters. Length matters more than punctuation."
          error={named.new_password}
        />
        <Field
          label="Confirm new password"
          type={showing ? "text" : "password"}
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => {
            setConfirm(event.target.value);
            setMismatch(false);
          }}
          error={mismatch ? "These two do not match." : undefined}
        />

        {/* The other half of the confirmation box: one catches a typo you cannot see, this
            lets you look. Neither replaces the other. */}
        <ShowPasswords
          showing={showing}
          onChange={setShowing}
          label="Show passwords"
        />

        <div>
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Changing…" : "Change password"}
          </Button>
        </div>
      </form>
    </section>
  );
}

function DeleteAccount() {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const remove = useDeleteAccount();
  const { signOut } = useAuth();

  return (
    <section aria-labelledby="delete-account" className="border-t pt-6">
      <h2 id="delete-account" className="mb-3 text-lg font-medium">
        Delete your account
      </h2>

      {!confirming ? (
        <>
          <p className="text-muted-foreground mb-3">
            This removes everything, permanently.
          </p>
          <Button variant="outline" onClick={() => setConfirming(true)}>
            Delete my account
          </Button>
        </>
      ) : (
        <form
          className="grid max-w-md gap-4"
          // The application says what is wrong in its own words. A native validation
          // bubble is neither, and it silently swallows the submit event.
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            remove.mutate(
              { password, confirmation: typed },
              // Signed out on the way past: the access token would otherwise keep
              // parsing for up to fifteen minutes against an account that no longer
              // exists, and every screen would render as though it were merely empty.
              { onSuccess: () => void signOut() },
            );
          }}
        >
          <Notice tone="failure" title="Delete your account?">
            Your plants, their photographs, every diagnosis and every
            conversation go with it. Plantopia will not be able to recover any
            of it, and neither will you.
          </Notice>

          {remove.isError ? (
            <Notice tone="failure">{readable(remove.error)}</Notice>
          ) : null}

          <Field
            label="Your password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />

          <Field
            label={`Type "${CONFIRMATION}" to confirm`}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            required
          />

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="destructive"
              disabled={remove.isPending}
            >
              {remove.isPending ? "Deleting…" : "Delete everything"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirming(false)}
            >
              Keep my account
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

/**
 * Every diagnosis this account has, across every plant, summed.
 *
 * `cost_usd` and `token_usage` are independently `null` when nothing was measured at
 * all, and the two `*_diagnosis_count` fields say whether the total is missing some of
 * an account's diagnoses — the same distinctions `TotalCost` draws on a single plant's
 * page, computed server-side here instead of over an array already in hand.
 */
function SpendSummary({ spend }: { spend: TotalSpend }) {
  return (
    <section aria-labelledby="spend" className="border-t pt-6">
      <h2 id="spend" className="mb-3 text-lg font-medium">
        What this has cost
      </h2>

      {spend.diagnosis_count === 0 ? (
        <p className="text-muted-foreground text-sm">Nothing diagnosed yet.</p>
      ) : !spend.cost_usd && !spend.token_usage ? (
        <p className="text-muted-foreground text-sm">Not yet measured.</p>
      ) : (
        <>
          <p className="text-sm">
            Across every plant and diagnosis:{" "}
            {[
              spend.token_usage
                ? `${spend.token_usage.total_tokens.toLocaleString()} tokens (${spend.token_usage.prompt_tokens.toLocaleString()} prompt, ${spend.token_usage.completion_tokens.toLocaleString()} completion)`
                : null,
              spend.cost_usd !== null ? `$${spend.cost_usd.toFixed(4)}` : null,
            ]
              .filter(Boolean)
              .join(" — ")}
          </p>
          {spend.costed_diagnosis_count < spend.diagnosis_count ||
          spend.tokened_diagnosis_count < spend.diagnosis_count ? (
            <p className="text-muted-foreground text-xs">
              Not every diagnosis recorded a full measurement; the total above
              covers only what was.
            </p>
          ) : null}
        </>
      )}
    </section>
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
