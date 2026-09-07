/**
 * Choosing which plant it is.
 *
 * The first place in the application where somebody is asked to arbitrate between two
 * machines. Most of what is tested here is about making that a fair question to ask: what
 * each answer was built from, how sure it is in words rather than a number, and that not
 * knowing is allowed.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const RUN = "01a0-run";
const PLANT = "01a0-plant";
const DIAGNOSIS = "01a0-diagnosis";

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

const TYPED = {
  common_name: "Holy basil",
  scientific_name: null,
  confidence: 1,
  method: "typed" as const,
};
const VISION = {
  common_name: "Basil",
  scientific_name: "Ocimum basilicum",
  confidence: 0.85,
  method: "vision" as const,
};
const PLANTNET = {
  common_name: "Thai basil",
  scientific_name: "Ocimum africanum",
  confidence: 0.71,
  method: "plantnet" as const,
};
const AGREED = {
  common_name: "Basil",
  scientific_name: "Ocimum basilicum",
  confidence: 0.9,
  method: "agreed" as const,
};

const STEP = `id: 1\nevent: step\ndata: {"step":"checking","description":"Checking the photographs"}\n\n`;

function pause(candidates: unknown[] | null): string {
  const block = candidates
    ? `,"identification":${JSON.stringify(candidates)}`
    : "";
  return (
    `id: 2\nevent: questions\ndata: {"questions":[` +
    `{"key":"watering","text":"How often do you water it?","kind":"text","options":[]}` +
    `]${block}}\n\n`
  );
}

function watching(frames: string[]) {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get("/api/v1/plants", () => HttpResponse.json([])),
    http.get(`/api/v1/runs/${RUN}`, () =>
      HttpResponse.json({
        id: RUN,
        plant_id: PLANT,
        kind: "diagnosis",
        status: "awaiting_answers",
        created_at: "2026-03-01T12:00:00Z",
        finished_at: null,
        diagnosis_id: null,
        error: null,
      }),
    ),
    http.get(`/api/v1/runs/${RUN}/events`, () => {
      const body = new TextEncoder().encode(frames.join(""));
      return new HttpResponse(body, {
        headers: { "Content-Type": "text/event-stream" },
      });
    }),
  );
}

function open() {
  return render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
}

describe("when the methods disagree", () => {
  it("asks which plant it is", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(
      await screen.findByRole("heading", { name: "Which plant is this?" }),
    ).toBeInTheDocument();
  });

  it("says how each answer was reached", async () => {
    // The provenance is the entire reason the choice is worth showing. A list of names with
    // nothing attached asks somebody to pick on nothing.
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByText(/Read from your photo/)).toBeInTheDocument();
    expect(
      screen.getByText(/Matched against a plant database/),
    ).toBeInTheDocument();
  });

  it("says how sure each one is in words", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByText(/very confident/)).toBeInTheDocument();
    expect(screen.getByText(/fairly confident/)).toBeInTheDocument();
  });

  it("puts no bare probability on the screen", async () => {
    // "0.71" invites being read as a measurement of how right the answer is. It is one
    // system's estimate on a scale that means nothing next to the other's.
    watching([STEP, pause([VISION, PLANTNET])]);

    open();
    await screen.findByRole("heading", { name: "Which plant is this?" });

    expect(screen.queryByText(/0\.71|0\.85|71%|85%/)).not.toBeInTheDocument();
  });

  it("shows the scientific name, which is what separates two plants with one common name", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByText("Ocimum basilicum")).toBeInTheDocument();
    expect(screen.getByText("Ocimum africanum")).toBeInTheDocument();
  });

  it("starts on the leading candidate", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    await screen.findByRole("radio", { checked: true });

    expect(screen.getAllByRole("radio", { checked: true })).toHaveLength(1);
  });

  it("says that leaving it alone is allowed", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByText(/leave it as it is/i)).toBeInTheDocument();
  });

  it("credits the service whose result is on screen", async () => {
    // A condition of the free tier, not a courtesy.
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByText(/powered by Pl@ntNet/i)).toBeInTheDocument();
  });

  it("says the two methods agreed, and names the one that can be named", async () => {
    // The strongest signal this step has, and the copy said the least about it: "a plant
    // database" gave an owner no way to tell one check from two. Agreement is worth
    // spelling out because it is *why* the confidence beside it is high — two methods that
    // do not share a mechanism reached the same answer.
    watching([STEP, pause([TYPED, AGREED])]);

    open();

    expect(
      await screen.findByText(
        /Your photo and Pl@ntNet's database independently agree, very confident/,
      ),
    ).toBeInTheDocument();
  });

  it("credits it when the agreement includes it", async () => {
    watching([STEP, pause([TYPED, AGREED])]);

    open();

    expect(await screen.findByText(/powered by Pl@ntNet/i)).toBeInTheDocument();
  });

  it("does not credit it when nothing of its is shown", async () => {
    watching([STEP, pause([TYPED, VISION])]);

    open();

    await screen.findByRole("heading", { name: "Which plant is this?" });
    expect(screen.queryByText(/Pl@ntNet/i)).not.toBeInTheDocument();
  });

  it("gives what somebody typed no confidence at all", async () => {
    // They are not estimating a likelihood, they are telling you what their plant is.
    watching([STEP, pause([TYPED, VISION])]);

    open();

    expect(await screen.findByText("What you told us")).toBeInTheDocument();
    expect(screen.queryByText(/What you told us, /)).not.toBeInTheDocument();
  });
});

describe("when they agree", () => {
  it("asks nothing about the species", async () => {
    watching([STEP, pause(null)]);

    open();

    await screen.findByLabelText("How often do you water it?");
    expect(
      screen.queryByRole("heading", { name: "Which plant is this?" }),
    ).not.toBeInTheDocument();
  });

  it("still asks the questions", async () => {
    watching([STEP, pause(null)]);

    open();

    expect(
      await screen.findByLabelText("How often do you water it?"),
    ).toBeInTheDocument();
  });
});

describe("submitting", () => {
  async function sentBy(action: () => Promise<void>) {
    let sent: unknown = null;
    server.use(
      http.post(`/api/v1/runs/${RUN}/answers`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          id: RUN,
          plant_id: PLANT,
          kind: "diagnosis",
          status: "queued",
          created_at: "2026-03-01T12:00:00Z",
          finished_at: null,
          diagnosis_id: DIAGNOSIS,
          error: null,
        });
      }),
    );
    await action();
    await waitFor(() => expect(sent).not.toBeNull());
    return sent as { species: unknown };
  }

  it("can be submitted without choosing anything", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);
    open();
    await screen.findByRole("heading", { name: "Which plant is this?" });

    expect(screen.getByRole("button", { name: "Carry on" })).toBeEnabled();
  });

  it("sends no species when the leader was left alone", async () => {
    // Sending the leader back would record that somebody confirmed it, which is a different
    // fact from nobody having disagreed.
    watching([STEP, pause([VISION, PLANTNET])]);

    const sent = await sentBy(async () => {
      open();
      await screen.findByRole("heading", { name: "Which plant is this?" });
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    expect(sent.species).toBeNull();
  });

  it("sends the one that was chosen instead", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    const sent = await sentBy(async () => {
      open();
      await userEvent.click(
        await screen.findByRole("radio", { name: /Thai basil/ }),
      );
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    expect(sent.species).toMatchObject({
      common_name: "Thai basil",
      method: "plantnet",
    });
  });

  it("sends what somebody typed when they stand by it", async () => {
    watching([STEP, pause([VISION, TYPED])]);

    const sent = await sentBy(async () => {
      open();
      await userEvent.click(
        await screen.findByRole("radio", { name: /Holy basil/ }),
      );
      await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    });

    expect(sent.species).toMatchObject({
      common_name: "Holy basil",
      method: "typed",
    });
  });
});

describe("without a pointer", () => {
  it("can be chosen from the keyboard", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);
    open();
    await screen.findByRole("heading", { name: "Which plant is this?" });

    const second = screen.getAllByRole("radio")[1]!;
    second.focus();
    await userEvent.keyboard(" ");

    await waitFor(() => expect(second).toBeChecked());
  });

  it("conveys the selection by more than colour", async () => {
    // The radio is what a screen reader reads and what makes the selection legible to
    // somebody who cannot separate the border colours.
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    const options = await screen.findAllByRole("radio");
    expect(options[0]!).toBeChecked();
    expect(options[1]!).not.toBeChecked();
  });

  it("groups the options so they are announced as one question", async () => {
    watching([STEP, pause([VISION, PLANTNET])]);

    open();

    expect(await screen.findByRole("radiogroup")).toHaveAccessibleName(
      "Which plant is this?",
    );
  });
});
