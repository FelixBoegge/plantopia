import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";

/**
 * Everything behind a session.
 *
 * The route somebody asked for is carried to the sign-in screen and returned to afterwards.
 * Landing on a grid after signing in, having asked for a particular plant, is a small thing
 * that reads as the application having forgotten.
 */
export function RequireSession() {
  const { state } = useAuth();
  const location = useLocation();

  if (state === "starting") {
    // Neither signed in nor out yet. Redirecting here would send somebody to sign in every
    // time they reloaded, a moment before the refresh cookie answered.
    return <p role="status">Loading…</p>;
  }

  if (state === "signed-out") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
