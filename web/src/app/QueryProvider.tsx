import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError, PROBLEM } from "@/api/problems";

/**
 * Server state, as a cache with invalidation — which is what it is.
 *
 * The alternative, a store mirroring the server, is a second copy that can disagree with
 * the first. Every screen here is a view of something the server owns.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A refusal is an answer, not a hiccup. Retrying a 404 or a quota refusal wastes
        // three round trips to arrive at the same sentence, and retrying a rate limit makes
        // the thing it is complaining about worse.
        retry: (failureCount, error) => {
          if (error instanceof ApiError) {
            const permanent = [
              PROBLEM.notFound,
              PROBLEM.unauthenticated,
              PROBLEM.sessionExpired,
              PROBLEM.quotaExceeded,
              PROBLEM.dailyCap,
              PROBLEM.rateLimited,
              PROBLEM.conflict,
              PROBLEM.invalidRequest,
              PROBLEM.invalidLink,
            ];
            if (permanent.some((type) => error.is(type))) return false;
          }
          return failureCount < 2;
        },
        staleTime: 30_000,
      },
    },
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // Created in state rather than at module scope, so each test gets its own cache and one
  // test cannot see what another fetched.
  const [client] = useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
