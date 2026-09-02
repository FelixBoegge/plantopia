import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/AppHeader";

/** The frame every signed-in screen shares. */
export function SignedIn() {
  return (
    <>
      <AppHeader />
      {/* Wider than it was. `max-w-5xl` left a third of a desktop screen empty and squeezed
          the plant page's two columns into each other — the chat in particular had barely
          room for a sentence per line. */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </>
  );
}
