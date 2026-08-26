import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { request } from "@/api/client";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { AuthShell } from "@/screens/auth/AuthShell";

type Outcome = "checking" | "verified" | "refused" | "no-token";

/**
 * Proving an address, by following the link that was emailed.
 *
 * Runs on arrival rather than behind a button. Somebody who has clicked a link in an email
 * has already expressed the intent; asking them to click again is asking twice.
 *
 * Every refusal reads the same, because the server answers unknown, expired and
 * already-used identically — a stranger holding a link should not learn from the refusal
 * whether it was ever real.
 */
export function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [outcome, setOutcome] = useState<Outcome>(
    token ? "checking" : "no-token",
  );
  const [failure, setFailure] = useState<string | null>(null);

  // Which token has already been sent. A verification link works exactly once, so a second
  // request spends it and the screen reports a refusal for a link that had just worked.
  // React's StrictMode runs this effect twice in development, which is how this was found —
  // but a remount for any reason would do the same to a real person's only link.
  const attempted = useRef<string | null>(null);

  useEffect(() => {
    if (!token || attempted.current === token) return;
    attempted.current = token;

    // No abandonment guard. The obvious one — a flag set in the cleanup — combines with the
    // ref above to drop the answer entirely: the first attempt is abandoned by StrictMode's
    // cleanup and the second is skipped as a duplicate, leaving the screen saying "checking"
    // for ever. Setting state after an unmount is a no-op in this version of React, which
    // is a far smaller problem than never showing a result.
    (async () => {
      try {
        await request("/auth/verify", { method: "POST", body: { token } });
        setOutcome("verified");
      } catch (error) {
        setFailure(readable(error));
        setOutcome("refused");
      }
    })();
  }, [token]);

  return (
    <AuthShell title="Verify your address">
      {outcome === "checking" ? <p role="status">Checking your link…</p> : null}

      {outcome === "verified" ? (
        <>
          <Notice title="Your address is confirmed">
            You can sign in now.
          </Notice>
          <Link to="/login">Sign in</Link>
        </>
      ) : null}

      {outcome === "refused" ? (
        <>
          <Notice tone="failure" title="That link cannot be used">
            {failure}
          </Notice>
          <p className="text-muted-foreground text-sm">
            Links expire, and each one works once. Registering again sends a new
            one.
          </p>
          <Link to="/register">Register</Link>
        </>
      ) : null}

      {outcome === "no-token" ? (
        <Notice tone="failure" title="Nothing to check">
          This page needs the link from your confirmation email.
        </Notice>
      ) : null}
    </AuthShell>
  );
}
