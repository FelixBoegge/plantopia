import { QueryClientProvider } from "@tanstack/react-query";
import { render as rtlRender } from "@testing-library/react";
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
 * A fresh query client per render, so one test cannot see what another fetched.
 */
export function render(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = makeQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>{children}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return rtlRender(ui, { wrapper: Wrapper });
}

export * from "@testing-library/react";
