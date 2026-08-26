/**
 * Getting in: signing in, proving an address, and recovering a password.
 *
 * The recurring property is what these screens must not reveal. The server answers
 * identically whether an address exists, whether a password was wrong, and whether a link
 * was ever real — and a screen that helpfully distinguished any of them would undo it.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
import { AppRoutes } from "@/routes/routes";
import { render, screen } from "@/test/render";
import { server } from "@/test/server";

const ACCOUNT = {
  id: "01a0-owner",
  email: "ada@example.com",
  created_at: "2026-03-01T12:00:00Z",
  tier: "free",
  role: "member",
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
  detail: "Those credentials were not accepted.",
};

function signedOut() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json(REFUSED, { status: 401 }),
    ),
  );
}

async function signInWith(
  email = "ada@example.com",
  password = "a-long-enough-password",
) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("signing in", () => {
  it("takes somebody to their plants", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    );

    render(<AppRoutes />, { route: "/login" });
    await signInWith();

    expect(
      await screen.findByRole("heading", { name: "Your plants" }),
    ).toBeInTheDocument();
  });

  it("returns to the screen that was asked for", async () => {
    // Landing on a grid having asked for a particular plant reads as the application
    // having forgotten.
    signedOut();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    );

    render(<AppRoutes />, { route: "/account" });
    await screen.findByRole("heading", { name: "Sign in" });
    await signInWith();

    expect(
      await screen.findByRole("heading", { name: "Your account" }),
    ).toBeInTheDocument();
  });

  it("does not say which half was wrong", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(REFUSED, { status: 401 }),
      ),
    );

    render(<AppRoutes />, { route: "/login" });
    await signInWith("nobody@example.com", "wrong-password-entirely");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Those credentials were not accepted.");
    expect(alert).not.toHaveTextContent(/password/i);
    expect(alert).not.toHaveTextContent(/no such/i);
    expect(alert).not.toHaveTextContent(/unverified/i);
  });

  it("stays on the sign-in screen when refused", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(REFUSED, { status: 401 }),
      ),
    );

    render(<AppRoutes />, { route: "/login" });
    await signInWith();

    await screen.findByRole("alert");
    expect(
      screen.getByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("asks the browser for the saved password rather than a new one", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/login" });

    expect(await screen.findByLabelText("Password")).toHaveAttribute(
      "autocomplete",
      "current-password",
    );
  });
});

describe("verifying an address", () => {
  it("checks the link on arrival rather than behind a button", async () => {
    // Somebody who clicked a link in an email has already expressed the intent. Asking
    // them to click again is asking twice.
    signedOut();
    let called = false;
    server.use(
      http.post("/api/v1/auth/verify", () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: "/verify-email?token=a-real-token" });

    expect(await screen.findByText(/confirmed/i)).toBeInTheDocument();
    expect(called).toBe(true);
  });

  it("offers signing in once the address is confirmed", async () => {
    signedOut();
    server.use(
      http.post(
        "/api/v1/auth/verify",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/verify-email?token=a-real-token" });

    expect(
      await screen.findByRole("link", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("says what to do about a link that cannot be used", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/verify", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidLink,
            title: "This link cannot be used",
            status: 400,
            detail:
              "The link is invalid, has expired, or has already been used.",
          },
          { status: 400 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/verify-email?token=spent" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /cannot be used/i,
    );
    expect(screen.getByText(/works once/i)).toBeInTheDocument();
  });

  it("shows the same thing for a spent link and one that never existed", async () => {
    // The server answers them identically — one sentence listing every possibility, so it
    // commits to none. What matters is that this screen shows what it was given rather than
    // inferring which case it was, so the two are the same to a stranger holding a link.
    signedOut();
    const refusal = {
      type: PROBLEM.invalidLink,
      title: "This link cannot be used",
      status: 400,
      detail: "The link is invalid, has expired, or has already been used.",
    };
    server.use(
      http.post("/api/v1/auth/verify", () =>
        HttpResponse.json(refusal, { status: 400 }),
      ),
    );

    const spent = render(<AppRoutes />, { route: "/verify-email?token=spent" });
    const first = (await screen.findByRole("alert")).textContent;
    spent.unmount();

    render(<AppRoutes />, { route: "/verify-email?token=never-issued" });
    const second = (await screen.findByRole("alert")).textContent;

    expect(second).toBe(first);
  });

  it("says so plainly when there is no link at all", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/verify-email" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /needs the link/i,
    );
  });
});

describe("asking for a reset link", () => {
  it("answers identically for an address with no account", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/reset/request", () =>
        HttpResponse.json({}, { status: 202 }),
      ),
    );

    render(<AppRoutes />, { route: "/reset-password" });
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Email"),
      "nobody@example.com",
    );
    await user.click(screen.getByRole("button", { name: "Send the link" }));

    const heading = await screen.findByRole("heading", {
      name: "Check your email",
    });
    expect(heading).toBeInTheDocument();
    expect(screen.queryByText(/no account/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not registered/i)).not.toBeInTheDocument();
  });
});

describe("choosing a new password", () => {
  it("says beforehand that it signs you out everywhere", async () => {
    // Better than surprising somebody whose other tab stops working.
    signedOut();

    render(<AppRoutes />, { route: "/reset-password?token=a-real-token" });

    expect(
      await screen.findByText(/signs you out everywhere/i),
    ).toBeInTheDocument();
  });

  it("confirms and offers signing in", async () => {
    signedOut();
    server.use(
      http.post(
        "/api/v1/auth/reset/confirm",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/reset-password?token=a-real-token" });
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("New password"),
      "a-brand-new-password",
    );
    await user.click(screen.getByRole("button", { name: "Set my password" }));

    expect(
      await screen.findByRole("heading", { name: "Your password is changed" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("says why a link was refused", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/reset/confirm", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidLink,
            title: "This link cannot be used",
            status: 400,
            detail:
              "The link is invalid, has expired, or has already been used.",
          },
          { status: 400 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/reset-password?token=spent" });
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("New password"),
      "a-brand-new-password",
    );
    await user.click(screen.getByRole("button", { name: "Set my password" }));

    // The server's own sentence, not a title this screen chose. The same notice also shows
    // a weak-password refusal, so a fixed heading here would be wrong half the time.
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The link is invalid, has expired, or has already been used.",
    );
  });
});

describe("a verification link is spent exactly once", () => {
  it("is sent once even when the effect runs twice", async () => {
    // React's StrictMode runs effects twice in development, and a remount would do the same
    // in production. A verification link works once: the second request spends it, and the
    // screen then reports a refusal for a link that had just worked. Found in a browser.
    signedOut();
    let attempts = 0;
    server.use(
      http.post("/api/v1/auth/verify", () => {
        attempts += 1;
        return attempts === 1
          ? new HttpResponse(null, { status: 204 })
          : HttpResponse.json(
              {
                type: PROBLEM.invalidLink,
                title: "This link cannot be used",
                status: 400,
                detail: "The link is invalid, has expired, or has already been used.",
              },
              { status: 400 },
            );
      }),
    );

    render(
      <StrictMode>
        <AppRoutes />
      </StrictMode>,
      { route: "/verify-email?token=a-real-token" },
    );

    expect(await screen.findByText(/confirmed/i)).toBeInTheDocument();
    expect(attempts).toBe(1);
  });
});
