import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { readable } from "@/api/problems";
import { useAuth } from "@/auth/AuthProvider";
import { Field } from "@/components/Field";
import { TextLink } from "@/components/TextLink";
import { ShowPasswords } from "@/components/ShowPasswords";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { AuthShell } from "@/screens/auth/AuthShell";

/**
 * Signing in.
 *
 * **One refusal for every reason.** The server does not say whether the address exists,
 * whether the password was wrong, or whether the account was ever verified, and this screen
 * shows what it says rather than guessing which it was.
 *
 * Somebody who arrived here because they asked for a particular screen is returned to it.
 */
export function SignIn() {
  const { state, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showing, setShowing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const wanted =
    (location.state as { from?: { pathname: string } } | null)?.from
      ?.pathname ?? "/";

  if (state === "signed-in") return <Navigate to={wanted} replace />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFailure(null);
    setBusy(true);
    try {
      await signIn(email, password);
      navigate(wanted, { replace: true });
    } catch (error) {
      setFailure(readable(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Sign in"
      description="Welcome back — pick up where you left off."
      footer={
        <>
          No account yet? <TextLink to="/register">Register</TextLink>
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
          type={showing ? "text" : "password"}
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {/* A wrong password here is otherwise discovered by being refused, which is a slow
            way to find out you typed it with caps lock on. */}
        <ShowPasswords showing={showing} onChange={setShowing} />

        {/* Recovery sits with the form it rescues rather than down beside registering:
            somebody who cannot remember their password is still trying to sign in. */}
        <div className="grid gap-3">
          <Button type="submit" className="h-10 text-base" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <TextLink to="/reset-password" className="text-center text-sm">
            Forgot your password?
          </TextLink>
        </div>
      </form>
    </AuthShell>
  );
}
