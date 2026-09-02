import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/AppHeader";

/** The frame every signed-in screen shares. */
export function SignedIn() {
  return (
    <>
      <AppHeader />
      {/* No maximum: the width follows the screen. Two fixed caps in a row still left a
          desktop with empty margins, and the two things that use this space — a grid of
          cards and a page with a chat column beside it — both get better the more of it
          they have. The padding grows with the viewport so the content never touches
          the edge. */}
      <main className="w-full px-4 py-8 sm:px-6 lg:px-10">
        <Outlet />
      </main>
    </>
  );
}
