import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/AppHeader";

/** The frame every signed-in screen shares. */
export function SignedIn() {
  return (
    <>
      <AppHeader />
      {/* A centred column, and a modest one.

          This was widened and then unwidened entirely, on the theory that a chat column
          beside the plant page needed the room. The chat has its own page now, so nothing
          here is competing for width — and a line of prose that runs the whole span of a
          wide monitor is harder to read, not easier. */}
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </>
  );
}
