import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { request } from "@/api/client";
import { readable } from "@/api/problems";
import { Field } from "@/components/Field";
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
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    setBusy(true);
    try {
      await request("/auth/reset/request", { method: "POST", body: { email } });
      setSent(true);
    } catch (error) {
      setFailure(readable(error));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
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
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 12 characters. Setting it signs you out everywhere else."
        />
        <Button type="submit" disabled={busy}>
          {busy ? "Setting it…" : "Set my password"}
        </Button>
      </form>
    </AuthShell>
  );
}
