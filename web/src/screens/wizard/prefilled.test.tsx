/**
 * Questions the run has already answered, and the one it refuses to continue without.
 *
 * Nobody is asked where the plant is before a run starts any more — the photograph usually
 * knows, and asking somebody to type what the file already says is asking them to do the
 * machine's work. What is left is this: a field already holding what was read, there to be
 * corrected rather than confirmed.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const RUN = "01a0-run";

const ACCOUNT = {
  id: "01a0-owner",
  email: "ada@example.com",
  created_at: "2026-03-01T12:00:00Z",
  tier: "free",
  role: "member",
  consent_version: "2026-08-25",
  consent_at: "2026-03-01T12:00:00Z",
  runs_used: 1,
  runs_allowed: 20,
  allowance_resets_at: "2026-04-01T00:00:00Z",
};

function question(overrides: Record<string, unknown> = {}) {
  return {
    key: "location",
    text: "Which town or city is the plant in?",
    kind: "text",
    options: [],
    prefill: null,
    prefill_note: null,
    required: false,
    ...overrides,
  };
}

const WATERING = question({
  key: "watering",
  text: "How often do you water it?",
  kind: "text",
});

function pausedAsking(...questions: unknown[]) {
  const frame =
    `id: 1\nevent: questions\ndata: ${JSON.stringify({ questions })}\n\n`;

  server.use(
    http.post("/api/v1/auth/refresh", () => HttpResponse.json({ access_token: "fresh" })),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get("/api/v1/plants", () => HttpResponse.json([])),
    http.get(`/api/v1/runs/${RUN}`, () =>
      HttpResponse.json({
        id: RUN,
        plant_id: null,
        kind: "diagnosis",
        status: "awaiting_answers",
        created_at: "2026-03-01T12:00:00Z",
        finished_at: null,
        diagnosis_id: null,
        error: null,
      }),
    ),
    http.get(`/api/v1/runs/${RUN}/events`, () =>
      new HttpResponse(new TextEncoder().encode(frame), {
        headers: { "Content-Type": "text/event-stream" },
      }),
    ),
  );
}

function open() {
  return render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
}

async function submitted(action: () => Promise<void>) {
  let sent: unknown = null;
  server.use(
    http.post(`/api/v1/runs/${RUN}/answers`, async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({
        id: RUN,
        plant_id: null,
        kind: "diagnosis",
        status: "queued",
        created_at: "2026-03-01T12:00:00Z",
        finished_at: null,
        diagnosis_id: null,
        error: null,
      });
    }),
  );
  await action();
  return () => sent as { answers: Record<string, string> } | null;
}

describe("an answer the run already has", () => {
  it("is in the field, not beside it", async () => {
    pausedAsking(question({ prefill: "Berlin" }));

    open();

    expect(await screen.findByLabelText(/Which town or city/)).toHaveValue("Berlin");
  });

  it("is submitted untouched", async () => {
    // The common case, and the one the prefill exists for: somebody who recognises their
    // own town confirms it by doing nothing.
    pausedAsking(question({ prefill: "Berlin" }));
    const sent = await submitted(async () => {
      open();
      await screen.findByLabelText(/Which town or city/);
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    await waitFor(() => expect(sent()).not.toBeNull());
    expect(sent()!.answers.location).toBe("Berlin");
  });

  it("can be corrected", async () => {
    pausedAsking(question({ prefill: "Berlin" }));
    const sent = await submitted(async () => {
      open();
      const field = await screen.findByLabelText(/Which town or city/);
      await userEvent.clear(field);
      await userEvent.type(field, "Munich");
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    await waitFor(() => expect(sent()).not.toBeNull());
    expect(sent()!.answers.location).toBe("Munich");
  });

  it("says where it came from", async () => {
    pausedAsking(
      question({ prefill: "Berlin", prefill_note: "Recorded by your camera" }),
    );

    open();

    expect(await screen.findByText("Recorded by your camera")).toBeInTheDocument();
  });

  it("credits the source its terms require crediting", async () => {
    pausedAsking(
      question({
        prefill: "Berlin",
        prefill_note: "Recorded by your camera, named by OpenStreetMap contributors",
      }),
    );

    open();

    expect(await screen.findByText(/OpenStreetMap contributors/)).toBeInTheDocument();
  });

  it("credits nothing when nothing was prefilled", async () => {
    pausedAsking(question());

    open();

    await screen.findByLabelText(/Which town or city/);
    expect(screen.queryByText(/OpenStreetMap/)).not.toBeInTheDocument();
  });

  it("describes the field by its note, so it is read with it", async () => {
    pausedAsking(
      question({ prefill: "Berlin", prefill_note: "Recorded by your camera" }),
    );

    open();

    expect(await screen.findByLabelText(/Which town or city/)).toHaveAccessibleDescription(
      "Recorded by your camera",
    );
  });
});

describe("a question that has to be answered", () => {
  it("says so in words rather than with a symbol", async () => {
    // An asterisk is a convention somebody has to already know, and it reads as nothing at
    // all to a screen reader.
    pausedAsking(question({ required: true }));

    open();

    expect(await screen.findByText("(needed)")).toBeInTheDocument();
  });

  it("is not marked wrong before anybody has tried anything", async () => {
    pausedAsking(question({ required: true }));

    open();

    await screen.findByLabelText(/Which town or city/);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("stops a submission while it is empty", async () => {
    pausedAsking(question({ required: true }));
    const sent = await submitted(async () => {
      open();
      await screen.findByLabelText(/Which town or city/);
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(sent()).toBeNull();
  });

  it("says which one, on the field itself", async () => {
    pausedAsking(question({ required: true }), WATERING);

    open();
    await screen.findByLabelText(/Which town or city/);
    await userEvent.click(screen.getByRole("button", { name: "Carry on" }));

    expect(await screen.findByLabelText(/Which town or city/)).toBeInvalid();
    expect(screen.getByLabelText(/How often do you water/)).not.toBeInvalid();
  });

  it("lets it through once it is filled in", async () => {
    pausedAsking(question({ required: true }));
    const sent = await submitted(async () => {
      open();
      await userEvent.type(
        await screen.findByLabelText(/Which town or city/),
        "Berlin",
      );
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    await waitFor(() => expect(sent()).not.toBeNull());
    expect(sent()!.answers.location).toBe("Berlin");
  });

  it("counts whitespace as empty", async () => {
    pausedAsking(question({ required: true }));
    const sent = await submitted(async () => {
      open();
      await userEvent.type(await screen.findByLabelText(/Which town or city/), "   ");
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(sent()).toBeNull();
  });

  it("leaves an optional one alone", async () => {
    // An indoor plant. Demanding a place there would be demanding it for nothing.
    pausedAsking(question({ required: false }));
    const sent = await submitted(async () => {
      open();
      await screen.findByLabelText(/Which town or city/);
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    await waitFor(() => expect(sent()).not.toBeNull());
    expect(sent()!.answers.location).toBeUndefined();
  });
});

describe("when the photograph was taken", () => {
  it("is a date field", async () => {
    pausedAsking(
      question({
        key: "captured_at",
        text: "When was the photograph taken?",
        kind: "date",
        prefill: "2026-08-10",
        prefill_note: "Recorded by your camera",
      }),
    );

    open();

    const field = await screen.findByLabelText(/When was the photograph taken/);
    expect(field).toHaveAttribute("type", "date");
    expect(field).toHaveValue("2026-08-10");
  });

  it("opens the calendar when the field is clicked", async () => {
    // Clicking a date input lands the caret in its day/month/year segments, so changing the
    // date meant typing it. The month view is already there — with the prefilled date
    // selected — behind a small icon most people never press.
    pausedAsking(
      question({
        key: "captured_at",
        text: "When was the photograph taken?",
        kind: "date",
        prefill: "2026-08-10",
      }),
    );

    open();
    const field = (await screen.findByLabelText(
      /When was the photograph taken/,
    )) as HTMLInputElement;
    // jsdom implements no picker at all, so the call is what is observable here.
    const opened = vi.fn();
    field.showPicker = opened;
    await userEvent.click(field);

    expect(opened).toHaveBeenCalled();
  });

  it("still opens nothing worse than nothing where there is no picker", async () => {
    // Firefox before 101 and any browser that refuses the call outside a gesture throw from
    // `showPicker`. An exception here would break typing a date, which is the fallback.
    pausedAsking(
      question({
        key: "captured_at",
        text: "When was the photograph taken?",
        kind: "date",
        prefill: "2026-08-10",
      }),
    );

    open();
    const field = (await screen.findByLabelText(
      /When was the photograph taken/,
    )) as HTMLInputElement;
    field.showPicker = () => {
      throw new Error("NotAllowedError");
    };

    await userEvent.click(field);

    expect(field).toHaveValue("2026-08-10");
  });

  it("can be cleared, which falls back to the upload date", async () => {
    pausedAsking(
      question({
        key: "captured_at",
        text: "When was the photograph taken?",
        kind: "date",
        prefill: "2026-08-10",
      }),
    );
    const sent = await submitted(async () => {
      open();
      await userEvent.clear(
        await screen.findByLabelText(/When was the photograph taken/),
      );
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    await waitFor(() => expect(sent()).not.toBeNull());
    // Sent as empty rather than omitted: absent means "never asked", and the run would
    // keep what the photograph said.
    expect(sent()!.answers.captured_at).toBe("");
  });
});
