/**
 * Ending a session, and starting one again on the same browser.
 *
 * What is cached belongs to whoever was signed in. Leaving it would show one person's
 * plants to the next, for as long as it took a query to refetch — and the first frame is
 * the one somebody sees.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { currentToken, forget } from "@/api/session";
import { PROBLEM } from "@/api/problems";
import { AppRoutes } from "@/routes/routes";
import { render, screen } from "@/test/render";
import { server } from "@/test/server";

const ADA = {
  id: "01a0-ada",
  email: "ada@example.com",
  created_at: "2026-03-01T12:00:00Z",
  tier: "free",
  role: "member" as const,
  consent_version: "2026-08-25",
  consent_at: "2026-03-01T12:00:00Z",
  runs_used: 0,
  runs_allowed: 20,
  allowance_resets_at: "2026-04-01T00:00:00Z",
};

const REFUSED = {
  type: PROBLEM.unauthenticated,
  title: "Not signed in",
  status: 401,
};

describe("signing out", () => {
  // Vitest fails a run on an unhandled rejection, but reports it against whichever test
  // happened to be in flight — which is how the cause of this one stayed hidden. Collected
  // here so the test that provokes it can assert on it directly.
  let unhandled: unknown[] = [];
  const collect = (reason: unknown) => {
    unhandled.push(reason);
  };

  beforeEach(() => {
    unhandled = [];
    process.on("unhandledRejection", collect);
  });
  afterEach(() => {
    process.off("unhandledRejection", collect);
  });

  it("returns to the sign-in screen", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ADA)),
      http.post(
        "/api/v1/auth/logout",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("forgets the token", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ADA)),
      http.post(
        "/api/v1/auth/logout",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(currentToken()).toBeNull();
  });

  it("signs somebody out even when the server cannot be told", async () => {
    // A sign-out that left somebody signed in because the network failed would be the worst
    // possible outcome of asking to be signed out.
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ADA)),
      http.post("/api/v1/auth/logout", () => HttpResponse.error()),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
    expect(currentToken()).toBeNull();
    // And the promise resolves. Telling the server is a courtesy; the sign-out has
    // happened locally either way, so there is nothing for a caller to handle. Rethrowing
    // left the button's click handler with a rejected promise nobody awaited — an
    // unhandled rejection that turned the whole suite red for a sign-out that worked.
    expect(unhandled).toEqual([]);
  });

  it("leaves nothing of the account behind", async () => {
    let asked = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => {
        asked += 1;
        return HttpResponse.json(ADA);
      }),
      http.post(
        "/api/v1/auth/logout",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    const first = render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByRole("heading", { name: "Sign in" });
    first.unmount();
    forget();

    // A second person on the same browser. Their account is fetched afresh rather than read
    // from what the first left behind.
    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(asked).toBeGreaterThan(1);
  });
});

describe("the header", () => {
  it("offers the evaluation screen only to an account that may reach it", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ADA)),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(
      screen.queryByRole("link", { name: "Evaluation" }),
    ).not.toBeInTheDocument();
  });

  it("offers it to an account that may", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () =>
        HttpResponse.json({ ...ADA, role: "admin" }),
      ),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(
      screen.getByRole("link", { name: "Evaluation" }),
    ).toBeInTheDocument();
  });

  it("uses real links, so a browser can do what browsers do with them", async () => {
    // Middle-click, open in a new tab, copy the address. A click handler on a styled div
    // has none of that and nobody notices until somebody tries.
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ADA)),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute(
      "href",
      "/account",
    );
  });

  it("is not shown to somebody who is signed out", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json(REFUSED, { status: 401 }),
      ),
    );

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Sign in" });

    expect(
      screen.queryByRole("navigation", { name: "Main" }),
    ).not.toBeInTheDocument();
  });
});
