/**
 * What is behind a session, and where somebody lands when they are not.
 *
 * The route asked for is carried to the sign-in screen and returned to afterwards. Landing
 * on a grid having asked for a particular plant is a small thing that reads as the
 * application having forgotten.
 */

import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
import { forget } from "@/api/session";
import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const ACCOUNT = {
  id: "01a0-owner",
  email: "ada@example.com",
  created_at: "2026-03-01T12:00:00Z",
  tier: "free",
  role: "member",
  consent_version: "2026-08-25",
  consent_at: "2026-03-01T12:00:00Z",
  runs_used: 2,
  runs_allowed: 20,
  allowance_resets_at: "2026-04-01T00:00:00Z",
};

function signedIn() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
  );
}

function signedOut() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json(
        { type: PROBLEM.unauthenticated, title: "Not signed in", status: 401 },
        { status: 401 },
      ),
    ),
  );
}

afterEach(forget);

describe("without a session", () => {
  it("sends somebody asking for their plants to sign in", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/" });

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("sends somebody asking for one plant to sign in too", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/plants/01a0-plant" });

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("leaves the sign-in screen reachable", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/login" });

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("leaves registering reachable", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/register" });

    expect(
      await screen.findByRole("heading", { name: "Register" }),
    ).toBeInTheDocument();
  });

  it("leaves verifying an address reachable", async () => {
    // Somebody following a link from their email has no session yet, by definition.
    signedOut();

    render(<AppRoutes />, { route: "/verify-email" });

    expect(
      await screen.findByRole("heading", { name: "Verify your address" }),
    ).toBeInTheDocument();
  });

  it("leaves resetting a password reachable", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/reset-password" });

    expect(
      await screen.findByRole("heading", { name: "Reset your password" }),
    ).toBeInTheDocument();
  });

  it("does not decide before the refresh cookie has answered", async () => {
    // Redirecting here would send somebody to sign in every time they reloaded, a moment
    // before the session was re-established.
    let answer: (value: unknown) => void = () => {};
    const held = new Promise((resolve) => {
      answer = resolve;
    });
    server.use(
      http.post("/api/v1/auth/refresh", async () => {
        await held;
        return HttpResponse.json({ access_token: "fresh" });
      }),
      http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
      http.get("/api/v1/plants", () => HttpResponse.json([])),
    );

    render(<AppRoutes />, { route: "/" });

    expect((await screen.findAllByRole("status"))[0]).toHaveTextContent(
      "Loading",
    );
    expect(
      screen.queryByRole("heading", { name: "Sign in" }),
    ).not.toBeInTheDocument();
    answer(null);
    expect(
      await screen.findByRole("heading", { name: "Your plants" }),
    ).toBeInTheDocument();
  });
});

describe("with a session", () => {
  it("shows the plants", async () => {
    signedIn();
    server.use(http.get("/api/v1/plants", () => HttpResponse.json([])));

    render(<AppRoutes />, { route: "/" });

    expect(
      await screen.findByRole("heading", { name: "Your plants" }),
    ).toBeInTheDocument();
  });

  it("shows one plant", async () => {
    signedIn();
    server.use(
      http.get("/api/v1/plants/01a0-plant", () =>
        HttpResponse.json({
          plant: {
            id: "01a0-plant",
            name: "Kitchen basil",
            species: null,
            species_confidence: null,
            location_kind: "indoor",
            location_text: null,
            photo_ref: null,
            created_at: "2026-03-01T12:00:00Z",
          },
          observations: [],
          diagnoses: [],
          roadmap_steps: [],
          feedback_due: false,
        }),
      ),
    );

    render(<AppRoutes />, { route: "/plants/01a0-plant" });

    expect(
      await screen.findByRole("heading", { name: "Kitchen basil" }),
    ).toBeInTheDocument();
  });

  it("shows the account", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });

    expect(
      await screen.findByRole("heading", { name: "Your account" }),
    ).toBeInTheDocument();
  });

  it("re-establishes the session without anything having been stored", async () => {
    // The refresh token is an httpOnly cookie the browser holds. Nothing in storage makes
    // this work, and that is the design rather than an omission.
    signedIn();

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(Object.keys(window.localStorage)).toHaveLength(0);
    expect(Object.keys(window.sessionStorage)).toHaveLength(0);
  });
});

describe("a route that does not exist", () => {
  it("goes somewhere rather than showing nothing", async () => {
    signedIn();

    server.use(http.get("/api/v1/plants", () => HttpResponse.json([])));

    render(<AppRoutes />, { route: "/nothing-here" });

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Your plants" }),
      ).toBeInTheDocument(),
    );
  });
});
