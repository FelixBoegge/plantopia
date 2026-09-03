/**
 * Talking about one plant.
 *
 * Two properties carry the weight. Every reply says what it consulted — a grounded answer
 * and one produced from the model's own knowledge look identical otherwise, and only one is
 * worth trusting about a plant somebody is worried about. And the reply survives a lost
 * connection, because the server runs it to completion whatever happens to the stream.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const PLANT_ID = "01a0-basil";

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

const DETAIL = {
  plant: {
    id: PLANT_ID,
    name: "Kitchen basil",
    species: null,
    species_confidence: null,
    location_kind: "indoor" as const,
    location_text: null,
    photo_ref: null,
    created_at: "2026-03-01T12:00:00Z",
  },
  observations: [],
  diagnoses: [],
  roadmap_steps: [],
  feedback_due: false,
};

function message(overrides: Record<string, unknown> = {}) {
  return {
    id: "01a0-message",
    plant_id: PLANT_ID,
    role: "assistant",
    content: "Probably overwatering.",
    tool_calls: null,
    created_at: "2026-03-02T12:00:00Z",
    ...overrides,
  };
}

function signedIn(messages: unknown[] = []) {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get(`/api/v1/plants/${PLANT_ID}`, () => HttpResponse.json(DETAIL)),
    http.get(`/api/v1/plants/${PLANT_ID}/messages`, () =>
      HttpResponse.json(messages),
    ),
  );
}

/** A stream of already-formed SSE frames, as the server would send them. */
function streaming(frames: string[], { delayMs = 0 } = {}) {
  server.use(
    http.post(`/api/v1/plants/${PLANT_ID}/messages/stream`, () => {
      const encoder = new TextEncoder();
      const body = new ReadableStream({
        async start(controller) {
          for (const frame of frames) {
            if (delayMs)
              await new Promise((resolve) => setTimeout(resolve, delayMs));
            controller.enqueue(encoder.encode(frame));
          }
          controller.close();
        },
      });
      return new HttpResponse(body, {
        headers: { "Content-Type": "text/event-stream" },
      });
    }),
  );
}

async function ask(question = "Why are the leaves yellow?") {
  const field = await screen.findByLabelText("Your question");
  await userEvent.type(field, question);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("getting to the conversation", () => {
  it("offers a way in from the plant", async () => {
    signedIn();

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}` });

    expect(
      await screen.findByRole("link", { name: "Chat about this plant" }),
    ).toHaveAttribute("href", `/plants/${PLANT_ID}/chat`);
  });

  it("does not put the conversation on the plant page any more", async () => {
    // It was a column there and is a page now. Leaving both would mean two transcripts of
    // the same conversation on screen at once, each fetching it.
    signedIn();

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}` });
    await screen.findByRole("link", { name: "Chat about this plant" });

    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
  });

  it("names the plant on the conversation's own page", async () => {
    // Arriving from a link, "Ask about this plant" alone does not say which.
    signedIn();

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(
      await screen.findByRole("heading", { name: "Kitchen basil", level: 1 }),
    ).toBeInTheDocument();
  });

  it("offers the way back", async () => {
    signedIn();

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(
      await screen.findByRole("link", { name: "Back to plant" }),
    ).toHaveAttribute("href", `/plants/${PLANT_ID}`);
  });
});

describe("the transcript", () => {
  it("shows what was said", async () => {
    signedIn([
      message({ id: "1", role: "user", content: "Why are the leaves yellow?" }),
      message({ id: "2" }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(
      await screen.findByText("Why are the leaves yellow?"),
    ).toBeInTheDocument();
    expect(screen.getByText("Probably overwatering.")).toBeInTheDocument();
  });

  it("says what a reply consulted, on the reply", async () => {
    signedIn([
      message({
        tool_calls: [
          {
            name: "search_plant_knowledge",
            args: { query: "yellow" },
            result: "…",
          },
        ],
      }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(
      await screen.findByText(/Consulted Plantopia's disorder reference/),
    ).toBeInTheDocument();
  });

  it("distinguishes an answer given without a lookup", async () => {
    // A grounded answer and one from the model's own knowledge look identical otherwise,
    // and only one of them is worth trusting about a plant somebody is worried about.
    signedIn([message({ tool_calls: null })]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(await screen.findByText(/without a lookup/)).toBeInTheDocument();
  });

  it("never names a lookup by its identifier", async () => {
    signedIn([
      message({
        tool_calls: [{ name: "search_plant_knowledge", args: {}, result: "" }],
      }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await screen.findByText(/Consulted/);

    expect(
      screen.queryByText(/search_plant_knowledge/),
    ).not.toBeInTheDocument();
  });

  it("names an unmapped lookup without exposing it either", async () => {
    signedIn([
      message({
        tool_calls: [{ name: "some_new_tool", args: {}, result: "" }],
      }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    expect(await screen.findByText(/another source/)).toBeInTheDocument();
    expect(screen.queryByText(/some_new_tool/)).not.toBeInTheDocument();
  });

  it("lists each source once however many times it was used", async () => {
    signedIn([
      message({
        tool_calls: [
          { name: "search_plant_knowledge", args: {}, result: "" },
          { name: "search_plant_knowledge", args: {}, result: "" },
        ],
      }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });

    const note = await screen.findByText(/Consulted/);
    expect(note.textContent?.match(/disorder reference/g)).toHaveLength(1);
  });

  it("does not render the agent's internal tool messages", async () => {
    // They are in the transcript so a reader can see what came back, not so a reader has to
    // scroll past them.
    signedIn([
      message({ id: "1", role: "tool", content: "raw corpus passage text" }),
      message({ id: "2" }),
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await screen.findByText("Probably overwatering.");

    expect(
      screen.queryByText("raw corpus passage text"),
    ).not.toBeInTheDocument();
  });
});

describe("asking something", () => {
  it("says which source is being consulted while it works", async () => {
    // Otherwise it is several seconds of silence, and silence reads as a failure.
    signedIn([]);
    streaming(
      [
        'event: tool\ndata: {"source":"the disorder reference"}\n\n',
        'event: completed\ndata: {"reply":"Probably overwatering.","escalated":false}\n\n',
      ],
      { delayMs: 30 },
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();

    expect(
      await screen.findByText(/Consulting the disorder reference/),
    ).toBeInTheDocument();
  });

  it("announces progress rather than merely showing it", async () => {
    signedIn([]);
    streaming(
      ['event: completed\ndata: {"reply":"Done.","escalated":false}\n\n'],
      {
        delayMs: 30,
      },
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();

    const live = document.querySelector("[aria-live='polite']");
    expect(live).toBeInTheDocument();
  });

  it("shows the reply from the transcript once it is done", async () => {
    // Refetched rather than assembled from the events: the server writes the transcript
    // either way, and rebuilding it here would be a second implementation of what a
    // conversation is.
    let asked = false;
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "fresh" }),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
      http.get(`/api/v1/plants/${PLANT_ID}`, () => HttpResponse.json(DETAIL)),
      http.get(`/api/v1/plants/${PLANT_ID}/messages`, () =>
        HttpResponse.json(
          asked ? [message({ content: "Probably overwatering." })] : [],
        ),
      ),
    );
    server.use(
      http.post(`/api/v1/plants/${PLANT_ID}/messages/stream`, () => {
        asked = true;
        return new HttpResponse(
          new TextEncoder().encode(
            'event: completed\ndata: {"reply":"Probably overwatering.","escalated":false}\n\n',
          ),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }),
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();

    expect(
      await screen.findByText("Probably overwatering."),
    ).toBeInTheDocument();
  });

  it("clears the box so the same question is not sent twice", async () => {
    signedIn([]);
    streaming([
      'event: completed\ndata: {"reply":"Done.","escalated":false}\n\n',
    ]);

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();

    await waitFor(() =>
      expect(screen.getByLabelText("Your question")).toHaveValue(""),
    );
  });

  it("refuses to send an empty question", async () => {
    signedIn([]);
    let sent = false;
    server.use(
      http.post(`/api/v1/plants/${PLANT_ID}/messages/stream`, () => {
        sent = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await screen.findByLabelText("Your question");

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(sent).toBe(false);
  });

  it("says the reply may still exist when the connection is lost", async () => {
    // It does. The server runs the turn to completion on its own thread, so a dropped
    // stream costs the view of the answer rather than the answer.
    signedIn([]);
    server.use(
      http.post(`/api/v1/plants/${PLANT_ID}/messages/stream`, () =>
        HttpResponse.error(),
      ),
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();

    expect(await screen.findByRole("alert")).toHaveTextContent(/may still be/i);
  });

  it("refetches the transcript even when the stream failed", async () => {
    signedIn([]);
    let refetches = 0;
    server.use(
      http.get(`/api/v1/plants/${PLANT_ID}/messages`, () => {
        refetches += 1;
        return HttpResponse.json([]);
      }),
      http.post(`/api/v1/plants/${PLANT_ID}/messages/stream`, () =>
        HttpResponse.error(),
      ),
    );

    render(<AppRoutes />, { route: `/plants/${PLANT_ID}/chat` });
    await ask();
    await screen.findByRole("alert");

    await waitFor(() => expect(refetches).toBeGreaterThan(1));
  });
});
