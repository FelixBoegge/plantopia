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
 * Thrown when the server could not be reached at all — as opposed to answering that the
 * session is over.
 *
 * The two used to be indistinguishable here, and the consequence was that restarting the
 * API, or closing a laptop on a train, signed somebody out of a session that was still
 * valid. A server that does not answer has told us nothing about the session.
 */
export class ServerUnreachableError extends Error {
  constructor() {
    super("Plantopia could not be reached.");
    this.name = "ServerUnreachableError";
  }
}

/** How many times a refused connection is retried, and how long between attempts. */
const ATTEMPTS = 3;
const BACKOFF_MS = [250, 1000];

/**
 * Obtain a new access token, or `null` if the session is over.
 *
 * Concurrent callers share one attempt. The promise is cleared once it settles so that a
 * later expiry starts a fresh one rather than reusing a resolved result.
 *
 * Throws `ServerUnreachableError` if the server never answered. That is not `null`: `null`
 * means the session ended and somebody must sign in again, and treating an unreachable
 * server as that would be signing them out over a dropped connection.
 */
export function renew(): Promise<string | null> {
  renewal ??= refresh().finally(() => {
    renewal = null;
  });
  return renewal;
}

async function refresh(): Promise<string | null> {
  for (let attempt = 0; attempt < ATTEMPTS; attempt++) {
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        // The refresh token is a cookie the browser holds and scripts cannot read. This is
        // what sends it.
        credentials: "include",
      });
    } catch {
      // Nothing answered. A few short retries cover the cases that pass on their own — a
      // dev server restarting, a connection dropping as a laptop wakes — and then it gives
      // up and says so, rather than deciding the session is over on the server's behalf.
      const wait = BACKOFF_MS[attempt];
      if (wait === undefined) break;
      await new Promise((resume) => setTimeout(resume, wait));
      continue;
    }

    if (!response.ok) {
      // The server answered, and its answer is that this session is finished.
      forget();
      onLost();
      return null;
    }

    const session = (await response.json()) as { access_token: string };
    token = session.access_token;
    return token;
  }

  // The token is left alone. It may well still be good, and the next attempt — a retry the
  // person asks for, or the next request — can use it.
  throw new ServerUnreachableError();
}
