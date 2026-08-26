/**
 * Creating an account.
 *
 * The property carrying the most weight is one about what the screen must *not* say: the
 * server answers identically whether or not an address is taken, and a message here that
 * distinguished them would undo that and turn the form into a way to ask who has an
 * account.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
import { Register } from "@/screens/auth/Register";
import { render, screen } from "@/test/render";
import { server } from "@/test/server";

const ACCEPTED = {
  detail:
    "If that address can be registered, a confirmation message is on its way.",
};

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

async function fillIn({
  email = "ada@example.com",
  password = "at-least-twelve-characters",
  consent = true,
} = {}) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  if (consent) await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "Create account" }));
  return user;
}

describe("registering", () => {
  it("tells the person to check their email rather than signing them in", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(ACCEPTED, { status: 202 }),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(
      await screen.findByRole("heading", { name: "Check your email" }),
    ).toBeInTheDocument();
  });

  it("sends what the person entered", async () => {
    signedOut();
    let sent: Record<string, unknown> = {};
    server.use(
      http.post("/api/v1/auth/register", async ({ request: incoming }) => {
        sent = (await incoming.json()) as Record<string, unknown>;
        return HttpResponse.json(ACCEPTED, { status: 202 });
      }),
    );

    render(<Register />);
    await fillIn({
      email: "ada@example.com",
      password: "a-long-enough-password",
    });

    expect(sent).toEqual({
      email: "ada@example.com",
      password: "a-long-enough-password",
      accepted_privacy_notice: true,
    });
  });

  it("answers a taken address exactly as a new one", async () => {
    // The server does this, and the screen must not undo it. Anything that distinguished
    // the two would answer "who has an account here?" to anybody who asked twice.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(ACCEPTED, { status: 202 }),
      ),
    );

    render(<Register />);
    await fillIn({ email: "already@example.com" });

    const shown = await screen.findByRole("heading", {
      name: "Check your email",
    });
    expect(shown).toBeInTheDocument();
    expect(screen.queryByText(/already/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/taken/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/exists/i)).not.toBeInTheDocument();
  });
});

describe("the privacy notice", () => {
  it("says what is stored, where it is sent, and what is inferred", async () => {
    signedOut();

    render(<Register />);

    expect(
      await screen.findByText(/photographs you upload/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/OpenRouter/)).toBeInTheDocument();
    expect(screen.getByText(/durable facts/i)).toBeInTheDocument();
  });

  it("says the inferred facts can be removed", async () => {
    // Otherwise it is a notice about something somebody cannot do anything about.
    signedOut();

    render(<Register />);

    expect(await screen.findByText(/see and remove/i)).toBeInTheDocument();
  });

  it("cannot be skipped", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "Invalid request",
            status: 400,
            detail: "the privacy notice must be agreed to",
          },
          { status: 400 },
        ),
      ),
    );

    render(<Register />);
    await fillIn({ consent: false });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /privacy notice/i,
    );
    expect(
      screen.queryByRole("heading", { name: "Check your email" }),
    ).not.toBeInTheDocument();
  });

  it("starts unchecked", async () => {
    // A pre-ticked consent box is not consent.
    signedOut();

    render(<Register />);

    expect(await screen.findByRole("checkbox")).not.toBeChecked();
  });
});

describe("when the server refuses", () => {
  it("says why, in the words the server used", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "Invalid request",
            status: 400,
            detail: "a password must be at least 12 characters",
          },
          { status: 400 },
        ),
      ),
    );

    render(<Register />);
    await fillIn({ password: "short" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "at least 12 characters",
    );
  });

  it("announces the failure rather than merely showing it", async () => {
    // A form that silently grows a red sentence is a form somebody using a screen reader
    // submits twice.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.rateLimited,
            title: "Too many attempts",
            status: 429,
            detail: "Wait.",
          },
          { status: 429 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("leaves what was typed so it can be corrected", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "Invalid",
            status: 400,
            detail: "Too short.",
          },
          { status: 400 },
        ),
      ),
    );

    render(<Register />);
    await fillIn({ email: "ada@example.com", password: "short" });

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Email")).toHaveValue("ada@example.com");
  });
});

describe("the form itself", () => {
  it("labels every field", async () => {
    // `getByLabelText` above only passes if they are bound. This says so on purpose.
    signedOut();

    render(<Register />);

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("asks the browser for a new password rather than an existing one", async () => {
    // A password manager offering the saved password on a registration form is offering
    // the wrong thing.
    signedOut();

    render(<Register />);

    expect(await screen.findByLabelText("Password")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
  });
});
