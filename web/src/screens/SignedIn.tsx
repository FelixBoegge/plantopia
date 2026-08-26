import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/AppHeader";

/** The frame every signed-in screen shares. */
export function SignedIn() {
  return (
    <>
      <AppHeader />
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
    </>
  );
}
