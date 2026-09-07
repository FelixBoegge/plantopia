/**
 * The account screen, and the one screen not everybody can reach.
 *
 * The account screen is the answer to a promise made at registration: that the facts
 * Plantopia infers about somebody can be seen and removed. A system that infers durable
 * facts and offers neither is one a person cannot correct.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

function account(overrides: Record<string, unknown> = {}) {
  return {
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
    may_read_evaluations: false,
    ...overrides,
  };
}

const FACT = {
  fact: "waters the kitchen basil about twice a week",
  source: "inferred" as const,
  confidence: 0.82,
  first_seen: "2026-03-02T12:00:00Z",
  last_confirmed: "2026-03-09T12:00:00Z",
};

function signedIn(who = account(), facts: unknown[] = []) {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(who)),
    http.get("/api/v1/profile/facts", () => HttpResponse.json(facts)),
  );
}

describe("the account", () => {
  it("shows who is signed in", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });

    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
  });

  it("shows what was agreed to, and when", async () => {
    // A system that cannot say what somebody consented to has no evidence of consent.
    signedIn();

    render(<AppRoutes />, { route: "/account" });

    expect(
      await screen.findByText(/privacy notice of 2026-08-25/),
    ).toBeInTheDocument();
  });

  it("shows how much of the allowance is left", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });

    expect(
      await screen.findByText(/2 of 20 diagnoses used this month/),
    ).toBeInTheDocument();
  });

  it("says plainly when there are none left", async () => {
    signedIn(account({ runs_used: 20 }));

    render(<AppRoutes />, { route: "/account" });

    expect(
      await screen.findByText("No diagnoses left this month"),
    ).toBeInTheDocument();
  });
});

describe("what has been learned", () => {
  it("lists each fact with when it was noticed", async () => {
    signedIn(account(), [FACT]);

    render(<AppRoutes />, { route: "/account" });

    expect(await screen.findByText(FACT.fact)).toBeInTheDocument();
    expect(screen.getByText(/first noticed/)).toBeInTheDocument();
  });

  it("says how sure it is in words rather than a number", async () => {
    // "0.82" alone invites being read as a certainty.
    signedIn(account(), [FACT]);

    render(<AppRoutes />, { route: "/account" });

    expect(await screen.findByText(/fairly sure/)).toBeInTheDocument();
    expect(screen.queryByText(/0\.82/)).not.toBeInTheDocument();
  });

  it("distinguishes what it was told from what it worked out", async () => {
    signedIn(account(), [
      { ...FACT, source: "stated", fact: "lives in Berlin" },
      FACT,
    ]);

    render(<AppRoutes />, { route: "/account" });

    expect(await screen.findByText(/You told it this/)).toBeInTheDocument();
    expect(screen.getByText(/It worked this out/)).toBeInTheDocument();
  });

  it("forgets one", async () => {
    let sent: unknown = null;
    let forgotten = false;
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(account())),
      http.get("/api/v1/profile/facts", () =>
        HttpResponse.json(forgotten ? [] : [FACT]),
      ),
      http.post(
        "/api/v1/profile/facts/forget",
        async ({ request: incoming }) => {
          sent = await incoming.json();
          forgotten = true;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: "Forget this" }),
    );

    await waitFor(() => expect(sent).toEqual({ fact: FACT.fact }));
  });

  it("stops showing a fact once it is forgotten", async () => {
    let forgotten = false;
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(account())),
      http.get("/api/v1/profile/facts", () =>
        HttpResponse.json(forgotten ? [] : [FACT]),
      ),
      http.post("/api/v1/profile/facts/forget", () => {
        forgotten = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: "Forget this" }),
    );

    await waitFor(() =>
      expect(screen.queryByText(FACT.fact)).not.toBeInTheDocument(),
    );
  });

  it("says so when nothing has been learned yet", async () => {
    signedIn(account(), []);

    render(<AppRoutes />, { route: "/account" });

    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
  });
});

describe("the evaluation screen", () => {
  const REPORT = "RAG Evaluation Report";

  it("is not offered to an account that cannot reach it", async () => {
    signedIn();
    server.use(http.get("/api/v1/plants", () => HttpResponse.json([])));

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(screen.queryByRole("link", { name: REPORT })).not.toBeInTheDocument();
  });

  it("is offered to an account the server says may reach it", async () => {
    // The server's answer, not the role. `AppHeader` used to compare `role` to "admin"
    // itself, which is a second copy of an authorization rule — and it was already wrong:
    // once a deployment could open the page to members, the page was reachable and the
    // navigation went on hiding the link. A member with the capability is exactly that
    // case, and is why this asserts on a member rather than an admin.
    signedIn(account({ may_read_evaluations: true }));
    server.use(http.get("/api/v1/plants", () => HttpResponse.json([])));

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    expect(await screen.findByRole("link", { name: REPORT })).toHaveAttribute(
      "href",
      "/admin/evaluation",
    );
  });

  it("sits between My plants and Account", async () => {
    // Position asserted rather than left to the eye. The bar is the only place this route
    // is discoverable, and "somewhere in the nav" is not the same as findable.
    signedIn(account({ may_read_evaluations: true }));
    server.use(http.get("/api/v1/plants", () => HttpResponse.json([])));

    render(<AppRoutes />, { route: "/" });
    await screen.findByRole("heading", { name: "Your plants" });

    const names = screen
      .getAllByRole("link")
      .map((link) => link.textContent?.trim());

    expect(names.indexOf(REPORT)).toBe(names.indexOf("My plants") + 1);
    expect(names.indexOf("Account")).toBe(names.indexOf(REPORT) + 1);
  });

  it("shows what a refused account is shown", async () => {
    // 404, the same as any route that does not exist. A screen that said "you may not"
    // would tell a stranger it is there.
    signedIn();
    server.use(
      http.get("/api/v1/evaluation/latest", () =>
        HttpResponse.json(
          {
            type: PROBLEM.notFound,
            title: "Not found",
            status: 404,
            detail: "No such resource.",
          },
          { status: 404 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/admin/evaluation" });

    expect(await screen.findByText("Not available")).toBeInTheDocument();
    expect(
      screen.queryByText(/permission|forbidden|not allowed/i),
    ).not.toBeInTheDocument();
  });

  it("renders the newest result for an account that may see it", async () => {
    signedIn(account({ role: "admin" }));
    server.use(
      http.get("/api/v1/evaluation/latest", () =>
        HttpResponse.json({
          generated_at: "2026-08-19T10:51:29Z",
          results: { accuracy: { top_1: 0.75, top_3: 0.89 } },
        }),
      ),
    );

    render(<AppRoutes />, { route: "/admin/evaluation" });

    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText("89%")).toBeInTheDocument();
  });

  it("says so plainly before any harness has run", async () => {
    // The ordinary state of a fresh clone. Failing here would send somebody looking for a
    // bug instead of a command.
    signedIn(account({ role: "admin" }));
    server.use(
      http.get("/api/v1/evaluation/latest", () =>
        HttpResponse.json({ generated_at: null, results: null }),
      ),
    );

    render(<AppRoutes />, { route: "/admin/evaluation" });

    expect(await screen.findByText("No results yet")).toBeInTheDocument();
    expect(screen.getByText(/eval\.run_eval/)).toBeInTheDocument();
  });
});

describe("before starting a diagnosis", () => {
  it("warns when the allowance is nearly gone", async () => {
    signedIn(account({ runs_used: 18 }));

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByText("2 diagnoses left this month"),
    ).toBeInTheDocument();
  });

  it("says so before rather than after when there are none left", async () => {
    // Being told by a failed diagnosis is being told too late.
    signedIn(account({ runs_used: 20 }));

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByText("No diagnoses left this month"),
    ).toBeInTheDocument();
  });

  it("does not let a diagnosis be started that would be refused", async () => {
    signedIn(account({ runs_used: 20 }));

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByRole("button", { name: "Start the diagnosis" }),
    ).toBeDisabled();
  });

  it("says nothing when there is plenty left", async () => {
    signedIn(account({ runs_used: 1 }));

    render(<AppRoutes />, { route: "/diagnose" });

    await screen.findByRole("button", { name: "Start the diagnosis" });
    expect(screen.queryByText(/left this month/)).not.toBeInTheDocument();
  });
});

describe("taking your data out", () => {
  it("offers a download", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });

    expect(
      await screen.findByRole("button", { name: /download my data/i }),
    ).toBeInTheDocument();
  });

  it("fetches it through the authenticated client rather than a bare link", async () => {
    // The access token lives in memory, not a cookie, so an anchor pointing at the
    // endpoint would arrive unauthenticated and download a 401 page named as an archive.
    signedIn();
    let authorised = false;
    server.use(
      http.get("/api/v1/me/export", ({ request }) => {
        authorised = request.headers.get("authorization") !== null;
        return new HttpResponse(new Blob(["zip-bytes"]), {
          headers: {
            "content-type": "application/zip",
            "content-disposition":
              'attachment; filename="plantopia-export-01a0.zip"',
          },
        });
      }),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /download my data/i }),
    );

    await waitFor(() => expect(authorised).toBe(true));
  });

  it("says so when it cannot be built", async () => {
    signedIn();
    server.use(
      http.get("/api/v1/me/export", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "That is too much to export at once",
            status: 413,
            detail:
              "this account holds more than can be exported in one request",
          },
          { status: 413 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /download my data/i }),
    );

    expect(
      await screen.findByText(/more than can be exported/i),
    ).toBeInTheDocument();
  });
});

describe("deleting your account", () => {
  it("asks twice before it will do anything", async () => {
    // The first click opens the form; nothing is sent until the form is completed. This is
    // the only action in the application with no undo.
    signedIn();
    let called = false;
    server.use(
      http.delete("/api/v1/me", () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );

    expect(called).toBe(false);
    expect(screen.getByLabelText("Your password")).toBeInTheDocument();
  });

  it("says what will be destroyed before it happens", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );

    const warning = screen.getByRole("alert");
    expect(warning).toHaveTextContent(/photographs/i);
    expect(warning).toHaveTextContent(/diagnosis|diagnoses/i);
    expect(warning).toHaveTextContent(/conversation/i);
  });

  it("can be backed out of", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /keep my account/i }),
    );

    expect(screen.queryByLabelText("Your password")).not.toBeInTheDocument();
  });

  it("sends the password and the typed confirmation", async () => {
    signedIn();
    let sent: Record<string, string> | null = null;
    server.use(
      http.delete("/api/v1/me", async ({ request }) => {
        sent = (await request.json()) as Record<string, string>;
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(
        "/api/v1/auth/logout",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );
    await userEvent.type(
      screen.getByLabelText("Your password"),
      "hunter2000000",
    );
    await userEvent.type(
      screen.getByLabelText(/to confirm/i),
      "delete my account",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /delete everything/i }),
    );

    await waitFor(() =>
      expect(sent).toEqual({
        password: "hunter2000000",
        confirmation: "delete my account",
      }),
    );
  });

  it("reports a refused password without losing what was typed", async () => {
    signedIn();
    server.use(
      http.delete("/api/v1/me", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "That was not confirmed",
            status: 400,
            detail: "that password is not correct",
          },
          { status: 400 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );
    await userEvent.type(
      screen.getByLabelText("Your password"),
      "wrong-password",
    );
    await userEvent.type(
      screen.getByLabelText(/to confirm/i),
      "delete my account",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /delete everything/i }),
    );

    expect(
      await screen.findByText(/password is not correct/i),
    ).toBeInTheDocument();
    // Still on the form, with the confirmation intact — retyping the phrase because the
    // password was mistyped would be a punishment for a typo.
    expect(screen.getByLabelText(/to confirm/i)).toHaveValue(
      "delete my account",
    );
  });

  it("signs out once the account is gone", async () => {
    // The access token would otherwise keep parsing for up to fifteen minutes against an
    // account that no longer exists, and every screen would render as merely empty.
    signedIn();
    server.use(
      http.delete("/api/v1/me", () => new HttpResponse(null, { status: 204 })),
      http.post(
        "/api/v1/auth/logout",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await userEvent.click(
      await screen.findByRole("button", { name: /delete my account/i }),
    );
    await userEvent.type(
      screen.getByLabelText("Your password"),
      "hunter2000000",
    );
    await userEvent.type(
      screen.getByLabelText(/to confirm/i),
      "delete my account",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /delete everything/i }),
    );

    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
});

describe("changing your password", () => {
  async function fillIn({
    current = "the-old-one",
    next = "a-new-long-password",
    confirm,
  }: { current?: string; next?: string; confirm?: string } = {}) {
    // Defaults to matching, because a mismatch is the exception these tests opt into.
    confirm ??= next;
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Current password"), current);
    await user.type(screen.getByLabelText("New password"), next);
    await user.type(screen.getByLabelText("Confirm new password"), confirm);
    await user.click(screen.getByRole("button", { name: "Change password" }));
    return user;
  }

  it("sends the current and the new password, and no address", async () => {
    // The only account this can change is the one already signed in.
    signedIn();
    let sent: Record<string, unknown> = {};
    server.use(
      http.post("/api/v1/auth/password", async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: "/account" });
    await fillIn();

    await waitFor(() =>
      expect(sent).toEqual({
        current_password: "the-old-one",
        new_password: "a-new-long-password",
      }),
    );
  });

  it("says so when it worked", async () => {
    signedIn();
    server.use(
      http.post(
        "/api/v1/auth/password",
        () => new HttpResponse(null, { status: 204 }),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await fillIn();

    expect(
      await screen.findByText(/password has been changed/i),
    ).toBeInTheDocument();
  });

  it("catches a mistyped confirmation without asking the server", async () => {
    // The confirmation exists to catch a typo in a box nobody can read back. Sending it
    // would hand the server a second copy of the same mistake.
    signedIn();
    let asked = false;
    server.use(
      http.post("/api/v1/auth/password", () => {
        asked = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: "/account" });
    await fillIn({ next: "a-new-long-password", confirm: "a-different-typo" });

    expect(
      await screen.findByText("These two do not match."),
    ).toBeInTheDocument();
    expect(asked).toBe(false);
  });

  it("puts a wrong current password under the box it is about", async () => {
    signedIn();
    server.use(
      http.post("/api/v1/auth/password", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "Invalid request",
            status: 400,
            detail: "that password is not correct",
            errors: [
              {
                location: ["body", "current_password"],
                message: "that password is not correct",
              },
            ],
          },
          { status: 400 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/account" });
    await fillIn();

    const field = await screen.findByLabelText("Current password");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription(/not correct/);
  });

  it("shows what was typed when asked to", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/account" });
    const field = await screen.findByLabelText("New password");
    expect(field).toHaveAttribute("type", "password");

    // By role, not by label: the checkbox renders a span carrying the role and a hidden
    // input beside it, and both answer to the label.
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Show passwords" }),
    );

    expect(field).toHaveAttribute("type", "text");
  });
});
