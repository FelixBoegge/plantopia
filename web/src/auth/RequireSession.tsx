import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";

/**
 * Everything behind a session.
 *
 * The route somebody asked for is carried to the sign-in screen and returned to afterwards.
 * Landing on a grid after signing in, having asked for a particular plant, is a small thing
 * that reads as the application having forgotten.
 */
export function RequireSession() {
  const { state, retry } = useAuth();
  const location = useLocation();

  if (state === "starting") {
    // Neither signed in nor out yet. Redirecting here would send somebody to sign in every
    // time they reloaded, a moment before the refresh cookie answered.
    return <p role="status">Loading…</p>;
  }

  if (state === "unreachable") {
    // Not a redirect to sign in. The server said nothing about the session, so sending
    // somebody to re-enter a password they never stopped being entitled to use would be
    // this screen inventing a fact it does not have.
    return (
      <div className="grid gap-3">
        <p role="status">
          Plantopia cannot be reached. Your session is still here — the server
          is not answering.
        </p>
        <div>
          <Button variant="outline" onClick={retry}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (state === "signed-out") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
