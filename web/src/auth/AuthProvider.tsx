import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import { request } from "@/api/client";
import type { Account, Session } from "@/api/types";
import {
  ServerUnreachableError,
  forget,
  onSessionLost,
  renew,
  setToken,
} from "@/api/session";

/**
 * Who is signed in, as far as the rest of the application is concerned.
 *
 * The token itself is deliberately not here — it lives in a module closure, so that a
 * renewal does not re-render the tree. What is here is the account, which changes rarely
 * and which screens genuinely read.
 */

/**
 * `unreachable` is not `signed-out`. The server never answered, so it has said nothing
 * about the session — and treating silence as an ended session signs people out over a
 * restarted API or a laptop waking from sleep.
 */
type State = "starting" | "signed-in" | "signed-out" | "unreachable";

interface Auth {
  state: State;
  account: Account | null;
  /** Try to re-establish the session after the server could not be reached. */
  retry: () => void;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshAccount: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queries = useQueryClient();
  const [state, setState] = useState<State>("starting");
  const [account, setAccount] = useState<Account | null>(null);
  // Bumped to re-run the effect below, which is the whole of what a retry is.
  const [attempt, setAttempt] = useState(0);

  const load = useCallback(async () => {
    const who = await request<Account>("/me");
    setAccount(who);
    setState("signed-in");
  }, []);

  const clear = useCallback(() => {
    forget();
    setAccount(null);
    setState("signed-out");
    // Everything cached belongs to whoever was signed in. Leaving it would show one
    // person's plants to the next on a shared browser, for as long as it took a query to
    // refetch — and the first frame is the one somebody sees.
    queries.clear();
  }, [queries]);

  useEffect(() => {
    // Re-establish from the refresh cookie. Nothing was stored to make this work: the
    // cookie is httpOnly and the browser sends it, which is the whole design.
    //
    // **Through `renew`, not by requesting `/auth/refresh` here.** Renewal is serialised in
    // one place precisely because each refresh rotates the token, and a second concurrent
    // one presents a token the first has already spent — which the server reads as a stolen
    // token being replayed and revokes the whole family. This effect running twice is not
    // hypothetical: StrictMode does it on every mount in development. The symptom was a
    // reload that worked, followed by a reload that signed the person out, and it was
    // invisible to the component suite because a mocked refresh endpoint has no rotation to
    // get wrong.
    onSessionLost(clear);
    (async () => {
      let token: string | null;
      try {
        token = await renew();
      } catch (error) {
        // Nothing answered after several tries. Say so and stop, rather than clearing a
        // session the server has not said anything about.
        if (error instanceof ServerUnreachableError) {
          setState("unreachable");
          return;
        }
        throw error;
      }
      if (token === null) return; // `renew` has already reported the loss.
      try {
        await load();
      } catch {
        clear();
      }
    })();
  }, [clear, load, attempt]);

  const value = useMemo<Auth>(
    () => ({
      state,
      account,
      retry: () => {
        setState("starting");
        setAttempt((n) => n + 1);
      },
      signIn: async (email, password) => {
        const session = await request<Session>("/auth/login", {
          method: "POST",
          body: { email, password },
        });
        setToken(session.access_token);
        await load();
      },
      signOut: async () => {
        try {
          await request("/auth/logout", { method: "POST" });
        } catch {
          // Swallowed rather than rethrown. Telling the server is a courtesy — it lets it
          // drop the refresh token early — and the sign-out itself has still happened
          // locally, so there is nothing for a caller to handle and no failure to report.
          //
          // Rethrowing left every caller with a rejected promise nobody awaited, which is
          // an unhandled rejection: the suite went red for a sign-out that worked.
        } finally {
          // Cleared whatever the server said. A sign-out that left somebody signed in
          // because the network failed would be the worst possible outcome of asking.
          clear();
        }
      },
      refreshAccount: load,
    }),
    [state, account, clear, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (auth === null)
    throw new Error("useAuth was called outside an AuthProvider");
  return auth;
}
