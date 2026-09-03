import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { request } from "@/api/client";
import { readable } from "@/api/problems";
import type { Accepted } from "@/api/types";
import { Field } from "@/components/Field";
import { ShowPasswords } from "@/components/ShowPasswords";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { AuthShell } from "@/screens/auth/AuthShell";

/**
 * Two screens in one route, chosen by whether a link brought you here.
 *
 * Without a token: ask where to send the link. **The answer is identical for an address
 * with no account** — the server behaves that way and this must not undo it.
 *
 * With a token: choose a new password. Doing so signs the person out everywhere, and saying
 * so beforehand is better than surprising somebody whose other tab stops working.
 */
export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token");
  return token ? <ChooseNew token={token} /> : <AskForLink />;
}

function AskForLink() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<Accepted | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    setBusy(true);
    try {
      setSent(
        await request<Accepted>("/auth/reset/request", {
          method: "POST",
          body: { email },
        }),
      );
    } catch (error) {
      setFailure(readable(error));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    // As on registration: what this says depends on how the deployment is configured, never
    // on whether the address has an account.
    return sent.email_configured === false ? (
      <AuthShell title="Check the server log">
        <Notice title="No email was sent">
          This deployment has no email provider configured, so the reset link
          was written to the application log instead of being sent anywhere.
        </Notice>
        <p className="text-muted-foreground text-sm">
          Look in the terminal running the API for a message with the subject
          “Reset your Plantopia password” and open the link in it. It works
          once, for the next hour.
        </p>
      </AuthShell>
    ) : (
      <AuthShell title="Check your email">
        <Notice title="On its way">
          If that address has an account, a reset link is on its way. It works
          once, for the next hour.
        </Notice>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Reset your password"
      description="We will email you a link to choose a new one."
      footer={<Link to="/login">Back to signing in</Link>}
    >
      <form onSubmit={submit} className="grid gap-6" noValidate>
        {failure ? <Notice tone="failure">{failure}</Notice> : null}
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Button type="submit" disabled={busy}>
          {busy ? "Sending…" : "Send the link"}
        </Button>
      </form>
    </AuthShell>
  );
}

function ChooseNew({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [showing, setShowing] = useState(false);
  const [done, setDone] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    setBusy(true);
    try {
      await request("/auth/reset/confirm", {
        method: "POST",
        body: { token, password },
      });
      setDone(true);
    } catch (error) {
      setFailure(readable(error));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthShell title="Your password is changed">
        <Notice title="Done">
          You have been signed out everywhere else. Sign in with your new
          password.
        </Notice>
        <Link to="/login">Sign in</Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Choose a new password">
      <form onSubmit={submit} className="grid gap-6" noValidate>
        {failure ? <Notice tone="failure">{failure}</Notice> : null}
        <Field
          label="New password"
          type={showing ? "text" : "password"}
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 12 characters. Setting it signs you out everywhere else."
        />
        {/* Worth more here than on sign-in: nobody knows this password yet, so there is
            nothing for a shoulder to look over, and a typo would be locked in behind a
            link that only works once. */}
        <ShowPasswords showing={showing} onChange={setShowing} />

        <Button type="submit" disabled={busy}>
          {busy ? "Setting it…" : "Set my password"}
        </Button>
      </form>
    </AuthShell>
  );
}
