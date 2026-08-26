import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { request } from "@/api/client";
import type { Account, Session } from "@/api/types";
import { forget, onSessionLost, setToken } from "@/api/session";

/**
 * Who is signed in, as far as the rest of the application is concerned.
 *
 * The token itself is deliberately not here — it lives in a module closure, so that a
 * renewal does not re-render the tree. What is here is the account, which changes rarely
 * and which screens genuinely read.
 */

type State = "starting" | "signed-in" | "signed-out";

interface Auth {
  state: State;
  account: Account | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshAccount: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>("starting");
  const [account, setAccount] = useState<Account | null>(null);

  const load = useCallback(async () => {
    const who = await request<Account>("/me");
    setAccount(who);
    setState("signed-in");
  }, []);

  const clear = useCallback(() => {
    forget();
    setAccount(null);
    setState("signed-out");
  }, []);

  useEffect(() => {
    // Re-establish from the refresh cookie. Nothing was stored to make this work: the
    // cookie is httpOnly and the browser sends it, which is the whole design.
    onSessionLost(clear);
    (async () => {
      try {
        const session = await request<Session>("/auth/refresh", { method: "POST" });
        setToken(session.access_token);
        await load();
      } catch {
        clear();
      }
    })();
  }, [clear, load]);

  const value = useMemo<Auth>(
    () => ({
      state,
      account,
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
  if (auth === null) throw new Error("useAuth was called outside an AuthProvider");
  return auth;
}
