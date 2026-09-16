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
import { render, screen, waitFor } from "@/test/render";
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

describe("where the link actually went", () => {
  it("sends somebody to their inbox when a provider is configured", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: true },
          { status: 202 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(
      await screen.findByRole("heading", { name: "Check your email" }),
    ).toBeInTheDocument();
  });

  it("does not claim a message was sent when nothing can send one", async () => {
    // The default deployment has no provider and writes the link to the application log
    // instead. "Check your email" then names the one place the link cannot be, which is
    // how somebody ends up in their spam folder looking for a message that was never sent.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: false },
          { status: 202 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(
      await screen.findByRole("heading", { name: "Check the server log" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/no email was sent/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Check your email" }),
    ).not.toBeInTheDocument();
  });

  it("still says the same thing for a taken address", async () => {
    // The fallback copy is about this deployment, never about this address. Copy that
    // varied with the address would undo what the identical response protects.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: false },
          { status: 202 },
        ),
      ),
    );

    render(<Register />);
    await fillIn({ email: "already@example.com" });

    await screen.findByRole("heading", { name: "Check the server log" });
    expect(screen.queryByText(/already/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/taken/i)).not.toBeInTheDocument();
  });

  it("offers a way to sign in once the address can be verified", async () => {
    // Whichever way somebody learns to verify — an inbox or the server log — they land
    // on a screen with no way back to the form that got them here.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: true },
          { status: 202 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toHaveAttribute("href", "/login");
  });

  it("offers the same way in from the server-log fallback", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: false },
          { status: 202 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toHaveAttribute("href", "/login");
  });
});

describe("a refusal lands on the control that caused it", () => {
  function refuses(field: string, message: string) {
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "Invalid request",
            status: 400,
            detail: message,
            errors: [{ location: ["body", field], message }],
          },
          { status: 400 },
        ),
      ),
    );
  }

  it("puts a missing agreement under the checkbox it is about", async () => {
    signedOut();
    refuses("accepted_privacy_notice", "the privacy notice must be agreed to");

    render(<Register />);
    await fillIn({ consent: false });

    const box = await screen.findByRole("checkbox");
    await waitFor(() => expect(box).toHaveAttribute("aria-invalid", "true"));
    const describedBy = box.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      /privacy notice/i,
    );
  });

  it("puts a rejected password under the password field", async () => {
    signedOut();
    refuses("password", "a password must be at least 12 characters");

    render(<Register />);
    await fillIn({ password: "short" });

    const field = await screen.findByLabelText("Password");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription(/at least 12 characters/);
  });

  it("does not repeat an attributed message at the top of the form", async () => {
    // Saying it twice is how a form teaches somebody to stop reading the top of it.
    signedOut();
    refuses("accepted_privacy_notice", "the privacy notice must be agreed to");

    render(<Register />);
    await fillIn({ consent: false });

    await screen.findByRole("alert");
    expect(screen.getAllByText(/privacy notice must be agreed/i)).toHaveLength(
      1,
    );
  });

  it("still shows a refusal that names no field at the top", async () => {
    // A rate limit belongs to the form, not to any one control.
    signedOut();
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          {
            type: PROBLEM.rateLimited,
            title: "Too many attempts",
            status: 429,
            detail: "Wait a minute before trying again.",
          },
          { status: 429 },
        ),
      ),
    );

    render(<Register />);
    await fillIn();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /wait a minute/i,
    );
  });

  it("clears a field message once the next attempt succeeds", async () => {
    signedOut();
    refuses("accepted_privacy_notice", "the privacy notice must be agreed to");

    render(<Register />);
    const user = await fillIn({ consent: false });
    await screen.findByRole("alert");

    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { ...ACCEPTED, email_configured: true },
          { status: 202 },
        ),
      ),
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByRole("heading", { name: "Check your email" }),
    ).toBeInTheDocument();
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
