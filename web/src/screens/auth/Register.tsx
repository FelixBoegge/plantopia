import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { request } from "@/api/client";
import { fieldMessages, readable } from "@/api/problems";
import type { Accepted } from "@/api/types";
import { Field } from "@/components/Field";
import { TextLink } from "@/components/TextLink";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { AuthShell } from "@/screens/auth/AuthShell";

/**
 * Creating an account.
 *
 * **The answer is the same whether or not the address is taken.** That is the server's
 * behaviour and this screen must not undo it — a message that said "already registered"
 * would turn the form into a way to ask who has an account here.
 *
 * Nobody is signed in by registering. The address has to be proven first, and saying so
 * plainly is better than a redirect to a screen that refuses them.
 *
 * **Where the link went depends on the deployment, so the screen asks rather than assumes.**
 * Without a provider configured the link is written to the application log, and telling
 * somebody to check their email then names the one place it cannot be.
 */
export function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consented, setConsented] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [sent, setSent] = useState<Accepted | null>(null);
  const [busy, setBusy] = useState(false);
  const consentErrorId = useId();
  const consentError = fieldErrors.accepted_privacy_notice;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    setFieldErrors({});
    setBusy(true);
    try {
      setSent(
        await request<Accepted>("/auth/register", {
          method: "POST",
          body: { email, password, accepted_privacy_notice: consented },
        }),
      );
    } catch (error) {
      const named = fieldMessages(error);
      setFieldErrors(named);
      // Only what the server did not pin to a control. Repeating an attributed message up
      // here would say the same thing twice, the second time away from the thing to change.
      setFailure(Object.keys(named).length > 0 ? null : readable(error));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    // Never varies with the address — only with how this deployment is configured. Copy
    // that differed for a taken address would undo the identical answer the server gives.
    return sent.email_configured === false ? (
      <AuthShell title="Check the server log">
        <Notice title="No email was sent">
          This deployment has no email provider configured, so the confirmation
          link was written to the application log instead of being sent
          anywhere.
        </Notice>
        <p className="text-muted-foreground text-sm">
          Look in the terminal running the API for a message with the subject
          “Confirm your Plantopia address” and open the link in it. The link
          works for the next 24 hours.
        </p>
        <Button
          className="h-10 text-base"
          nativeButton={false}
          render={<Link to="/login" />}
        >
          Sign in
        </Button>
      </AuthShell>
    ) : (
      <AuthShell title="Check your email">
        <Notice title="Almost there">
          If that address can be registered, a confirmation message is on its
          way. Follow the link in it to finish setting up your account.
        </Notice>
        <p className="text-muted-foreground text-sm">
          The link works for the next 24 hours.
        </p>
        <Button
          className="h-10 text-base"
          nativeButton={false}
          render={<Link to="/login" />}
        >
          Sign in
        </Button>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Register"
      description="Diagnose a plant, keep its history, and ask about it afterwards."
      footer={
        <>
          Already have an account? <TextLink to="/login">Sign in</TextLink>
        </>
      }
    >
      <form onSubmit={submit} className="grid gap-4" noValidate>
        {failure ? <Notice tone="failure">{failure}</Notice> : null}

        <Field
          label="Email"
          className="h-10 md:text-base"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          label="Password"
          className="h-10 md:text-base"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="At least 12 characters. Length matters more than punctuation."
          error={fieldErrors.password}
        />

        <div className="grid gap-3">
          <div className="flex items-start gap-3">
            <Checkbox
              id="consent"
              checked={consented}
              aria-invalid={consentError ? true : undefined}
              aria-describedby={consentError ? consentErrorId : undefined}
              onCheckedChange={(value) => setConsented(value === true)}
            />
            <Label
              htmlFor="consent"
              className="text-sm leading-relaxed font-normal"
            >
              I agree to the privacy notice below.
            </Label>
          </div>
          {/* Under the box it is about, not at the top of the form: a message about a
              control somebody has to scroll back to is a message they have to hold in their
              head on the way there. */}
          {consentError ? (
            <p
              id={consentErrorId}
              role="alert"
              className="text-destructive text-sm"
            >
              {consentError}
            </p>
          ) : null}
          {/* The notice scrolls inside its own box rather than stretching the card past
              the bottom of a laptop screen. It stays present, at a readable size, and
              nothing is hidden behind an interaction — which is what the checkbox above
              means by "below", and is the point of showing it on the screen where consent
              is given. Bounded height also means the card does not grow the next time the
              notice gains a paragraph. */}
          <div className="text-muted-foreground grid max-h-28 gap-2 overflow-y-auto rounded-lg bg-background/40 p-3 text-sm [@media(min-height:880px)]:max-h-40">
            <p>
              Plantopia stores the photographs you upload, what you write, and
              the diagnoses it produces. Photographs and text are sent to
              language models routed through OpenRouter in order to answer.
            </p>
            <p>
              It also infers and keeps durable facts about how you care for your
              plants — how often you water, where things live — and uses them in
              later answers. You can see and remove any of them from your
              account at any time.
            </p>
          </div>
        </div>

        <Button type="submit" className="h-10 text-base" disabled={busy}>
          {busy ? "Creating your account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
