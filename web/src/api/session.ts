/**
 * Where the access token lives, and how it is renewed.
 *
 * **In a module closure.** Not React state, which would re-render the tree on every
 * renewal; and not `localStorage` or `sessionStorage`, which any injected script can read —
 * the refresh token is an httpOnly cookie precisely so that a script cannot reach it, and
 * putting the access token in storage would give back most of what that buys.
 *
 * Losing it on reload is not a problem: the refresh cookie re-establishes the session, which
 * is what it is for.
 *
 * **Renewal is serialised, and that is the subtlest thing here.** Several requests failing
 * together must produce one refresh. Each refresh rotates the token, so a second concurrent
 * one presents a token the first has already spent — which the server correctly reads as a
 * stolen token being replayed and ends the session for everybody holding it. A page that
 * fires four queries on mount would sign the person out.
 */

let token: string | null = null;
let renewal: Promise<string | null> | null = null;

/** Called when a session cannot be recovered, so the application can send somebody to sign in. */
let onLost: () => void = () => {};

export function setToken(next: string | null): void {
  token = next;
}

export function currentToken(): string | null {
  return token;
}

export function onSessionLost(handler: () => void): void {
  onLost = handler;
}

export function forget(): void {
  token = null;
  renewal = null;
}

/**
 * Obtain a new access token, or `null` if the session is over.
 *
 * Concurrent callers share one attempt. The promise is cleared once it settles so that a
 * later expiry starts a fresh one rather than reusing a resolved result.
 */
export function renew(): Promise<string | null> {
  renewal ??= refresh().finally(() => {
    renewal = null;
  });
  return renewal;
}

async function refresh(): Promise<string | null> {
  try {
    const response = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      // The refresh token is a cookie the browser holds and scripts cannot read. This is
      // what sends it.
      credentials: "include",
    });
    if (!response.ok) {
      forget();
      onLost();
      return null;
    }
    const session = (await response.json()) as { access_token: string };
    token = session.access_token;
    return token;
  } catch {
    // A network failure is not a lost session — but there is no token to work with either,
    // and pretending otherwise would retry forever.
    forget();
    onLost();
    return null;
  }
}
