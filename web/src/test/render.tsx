import { QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender } from "@testing-library/react";
import { StrictMode } from "react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { makeQueryClient } from "@/app/QueryProvider";
import { AuthProvider } from "@/auth/AuthProvider";

/**
 * Render a screen the way the application renders it.
 *
 * A test that assembled its own providers would be a test of a different tree than the one
 * that ships — and the differences would be exactly the wiring most worth exercising.
 *
 * **`StrictMode`, because `main.tsx` uses it.** It runs every effect twice on mount, which
 * is not a quirk to be worked around but the cheapest available check that an effect can be
 * run twice safely. Omitting it here meant the suite mounted a tree the application never
 * mounts: a startup that fired two concurrent token renewals passed every test and signed
 * people out of the real application on their second reload.
 *
 * A fresh query client per render, so one test cannot see what another fetched.
 */
export function render(
  ui: ReactElement,
  { route = "/" }: { route?: string } = {},
) {
  const client = makeQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StrictMode>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[route]}>
            <AuthProvider>{children}</AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>
    );
  }

  return rtlRender(ui, { wrapper: Wrapper });
}

export * from "@testing-library/react";
