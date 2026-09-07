/**
 * Starting a diagnosis and watching it happen.
 *
 * The wizard is the centrepiece and the hardest thing here to be sure of, because what
 * makes it good — a connection held open across a pause, a reload that loses nothing — is
 * exactly what a mocked fetch makes look easy. These cover what can be covered here; the
 * browser runs in group 8 cover the rest.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
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
  runs_used: 0,
  runs_allowed: 20,
  allowance_resets_at: "2026-04-01T00:00:00Z",
};

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: RUN,
    plant_id: null,
    kind: "diagnosis",
    status: "running",
    created_at: "2026-03-01T12:00:00Z",
    finished_at: null,
    diagnosis_id: null,
    error: null,
    ...overrides,
  };
}

const DETAIL = {
  diagnosis: {
    id: DIAGNOSIS,
    plant_id: PLANT,
    observation_id: "01a0-observation",
    is_healthy: false,
    reasoning: "The lower leaves are yellowing from the base upward.",
    candidates: [
      {
        disorder_id: "underwatering",
        name: "Underwatering",
        probability: 0.21,
        severity: "monitor",
        supporting_evidence: ["Soil pulls away from the pot"],
        contradicting_evidence: [],
        distinguishing_test:
          "Water thoroughly and watch for overnight recovery.",
      },
      {
        disorder_id: "overwatering",
        name: "Overwatering",
        probability: 0.62,
        severity: "act_this_week",
        supporting_evidence: ["Soil is wet a week after watering"],
        contradicting_evidence: ["No smell of rot"],
        distinguishing_test: "Lift the pot — it should feel light when dry.",
      },
    ],
    created_at: "2026-03-02T12:00:00Z",
    cost_usd: 0.04,
    token_usage: null,
    sources: [],
  },
  roadmap_steps: [
    {
      id: "01a0-step",
      diagnosis_id: DIAGNOSIS,
      ordinal: 1,
      action: "Stop watering until the top 3cm are dry",
      rationale: "Roots need air as much as water.",
      success_signal: "New growth stops yellowing.",
      tier: 1,
      due_date: "2026-03-09T12:00:00Z",
      status: "pending",
      completed_at: null,
    },
  ],
};

function signedIn() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
  );
}

function streamOf(...text: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const frame of text) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
}

function watching(frames: string[], runState = run()) {
  server.use(
    http.get(`/api/v1/runs/${RUN}`, () => HttpResponse.json(runState)),
    http.get(
      `/api/v1/runs/${RUN}/events`,
      () =>
        new HttpResponse(streamOf(...frames), {
          headers: { "Content-Type": "text/event-stream" },
        }),
    ),
  );
}

const STEP =
  'id: 1\nevent: step\ndata: {"step":"checking","description":"Checking the photographs"}\n\n';
const QUESTIONS =
  'id: 2\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often do you water it?","kind":"text","options":[]},{"key":"drainage","text":"Does the pot have drainage holes?","kind":"choice","options":["Drainage holes, no saucer","No drainage holes"]}]}\n\n';
const COMPLETED = `id: 3\nevent: completed\ndata: {"diagnosis_id":"${DIAGNOSIS}","plant_id":"${PLANT}","rejected":false,"reason":null}\n\n`;

describe("starting a diagnosis", () => {
  it("is headed by the same words as every link that leads here", async () => {
    // The nav and the plants list both offer "Diagnose a plant". Landing on a screen headed
    // something else reads as having arrived somewhere other than where you clicked.
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByRole("heading", { name: "Diagnose a plant" }),
    ).toBeInTheDocument();
  });

  it("offers a labelled button rather than a bare file input", async () => {
    // A browser's own file control is a small grey rectangle whose label is set by the
    // browser, not by us. It does not read as the first thing to do on the screen.
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByLabelText("Upload images"),
    ).toBeInTheDocument();
  });

  it("shows a card naming each image once it has been chosen", async () => {
    // Confirmation that the right files were picked, before a run that costs money starts
    // on the wrong ones.
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });
    await userEvent.upload(await screen.findByLabelText("Upload images"), [
      new File(["png"], "whole-plant.png", { type: "image/png" }),
      new File(["png"], "close-up.png", { type: "image/png" }),
    ]);

    expect(await screen.findByText("whole-plant.png")).toBeInTheDocument();
    expect(screen.getByText("close-up.png")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent(/2 images/i);
  });

  it("says what it will accept before a file is chosen", async () => {
    // Otherwise the limits are learned from a refusal, after somebody has waited for an
    // upload of four photographs to finish.
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByText(/Up to 4 images, PNG or JPEG, 8 MB each/),
    ).toBeInTheDocument();
  });

  it("offers only the formats the server recognises", async () => {
    // `image/*` invited a HEIC straight off an iPhone, which the server refuses by magic
    // bytes after the upload.
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });

    expect(await screen.findByLabelText("Upload images")).toHaveAttribute(
      "accept",
      "image/png,image/jpeg",
    );
  });

  it("does not start one until it is asked to", async () => {
    // A run costs real money and takes a minute and a half. Starting one as a side effect
    // of choosing a file is a bill nobody agreed to.
    signedIn();
    let started = false;
    server.use(
      http.post("/api/v1/runs", () => {
        started = true;
        return HttpResponse.json(run());
      }),
    );

    render(<AppRoutes />, { route: "/diagnose" });
    const picker = await screen.findByLabelText("Upload images");
    await userEvent.upload(
      picker,
      new File(["png"], "leaf.png", { type: "image/png" }),
    );

    expect(started).toBe(false);
  });

  it("shows back what was chosen", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });
    const picker = await screen.findByLabelText("Upload images");
    await userEvent.upload(
      picker,
      new File(["png"], "leaf.png", { type: "image/png" }),
    );

    expect(await screen.findByText("leaf.png")).toBeInTheDocument();
  });

  it("cannot be submitted without a photograph", async () => {
    signedIn();

    render(<AppRoutes />, { route: "/diagnose" });

    expect(
      await screen.findByRole("button", { name: "Start the diagnosis" }),
    ).toBeDisabled();
  });

  it("sends the photographs and where the plant lives", async () => {
    signedIn();
    let sent: FormData | null = null;
    server.use(
      http.post("/api/v1/runs", async ({ request: incoming }) => {
        sent = await incoming.formData();
        return HttpResponse.json(run());
      }),
      http.get(`/api/v1/runs/${RUN}`, () => HttpResponse.json(run())),
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(streamOf(STEP), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    render(<AppRoutes />, { route: "/diagnose" });
    await userEvent.upload(
      await screen.findByLabelText("Upload images"),
      new File(["png"], "leaf.png", { type: "image/png" }),
    );
    const submit = screen.getByRole("button", { name: "Start the diagnosis" });
    expect(submit).toBeEnabled(); // it was disabled until a photograph was chosen
    await userEvent.click(submit);

    await waitFor(() => expect(sent).not.toBeNull());
    // No name is sent: nobody is asked to name a plant they came here to have identified,
    // and the run names it from what the identification found.
    expect(sent!.get("plant_name")).toBeNull();
    expect(sent!.get("location_kind")).toBe("indoor");
    expect(sent!.getAll("photographs")).toHaveLength(1);
  });

  it("says why a photograph was refused, and starts nothing", async () => {
    signedIn();
    server.use(
      http.post("/api/v1/runs", () =>
        HttpResponse.json(
          {
            type: PROBLEM.invalidRequest,
            title: "That photograph could not be used",
            status: 400,
            detail:
              "Unsupported image format. Please upload a PNG, JPEG or WebP photo.",
          },
          { status: 400 },
        ),
      ),
    );

    // Named and typed as an image, so the picker accepts it — the server is what refuses
    // it, having looked at the bytes. A file the picker itself rejects never gets this far,
    // which is a different and lesser case.
    render(<AppRoutes />, { route: "/diagnose" });
    await userEvent.upload(
      await screen.findByLabelText("Upload images"),
      new File(["not really a png"], "leaf.png", { type: "image/png" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Start the diagnosis" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Unsupported image format/,
    );
    expect(
      screen.getByRole("button", { name: "Start the diagnosis" }),
    ).toBeInTheDocument();
  });

  it("says when the allowance is used up", async () => {
    signedIn();
    server.use(
      http.post("/api/v1/runs", () =>
        HttpResponse.json(
          {
            type: PROBLEM.quotaExceeded,
            title: "Monthly allowance reached",
            status: 429,
            detail: "This account has used its runs for the current period.",
            limit: 20,
            used: 20,
            resets_at: "2026-04-01T00:00:00Z",
          },
          { status: 429 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/diagnose" });
    await userEvent.upload(
      await screen.findByLabelText("Upload images"),
      new File(["png"], "leaf.png", { type: "image/png" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Start the diagnosis" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/used its runs/);
  });
});

describe("watching it work", () => {
  it("puts the activity beside the run rather than above it", async () => {
    // jsdom lays nothing out, so what is assertable is the structure: the activity and the
    // run body are siblings of a two-column grid rather than stacked blocks.
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    const activity = await screen.findByRole("region", {
      name: "What Plantopia is doing",
    });

    expect(activity.parentElement).toHaveClass("lg:grid-cols-[18rem_1fr]");
  });

  it("puts the activity first, so it leads when the columns stack", async () => {
    // On a phone during a ninety-second run, the progress is the screen.
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    const activity = await screen.findByRole("region", {
      name: "What Plantopia is doing",
    });

    expect(activity.parentElement?.firstElementChild).toBe(activity);
  });


  it("shows each step as it arrives", async () => {
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText("Checking the photographs"),
    ).toBeInTheDocument();
  });

  it("keeps earlier steps as later ones arrive", async () => {
    signedIn();
    watching([
      STEP,
      'id: 2\nevent: step\ndata: {"step":"identifying","description":"Identifying the species"}\n\n',
    ]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText("Identifying the species"),
    ).toBeInTheDocument();
    expect(screen.getByText("Checking the photographs")).toBeInTheDocument();
  });

  it("says it is still working between steps", async () => {
    // The slowest part of a run is one model call that can take a minute. Silence there
    // reads as a stall.
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText(/Working…|Reconnecting…/),
    ).toBeInTheDocument();
  });

  it("announces progress to a reader who cannot see it", async () => {
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByText("Checking the photographs");

    expect(document.querySelector("[aria-live='polite']")).toBeInTheDocument();
  });

  it("never shows an internal name", async () => {
    signedIn();
    watching([STEP, COMPLETED]);
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByText("Checking the photographs");

    expect(
      screen.queryByText(/identify_plant|guard_input|check_contagion/),
    ).not.toBeInTheDocument();
  });
});

describe("when it asks something", () => {
  it("shows the questions without losing the progress", async () => {
    signedIn();
    watching([STEP, QUESTIONS], run({ status: "awaiting_answers" }));

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByLabelText("How often do you water it?"),
    ).toBeInTheDocument();
    expect(screen.getByText("Checking the photographs")).toBeInTheDocument();
  });

  it("moves focus to the questions", async () => {
    // The one moment in a run where the person is expected to do something. Somebody using
    // a keyboard would otherwise have to hunt for where.
    signedIn();
    watching([STEP, QUESTIONS], run({ status: "awaiting_answers" }));

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    const heading = await screen.findByRole("heading", {
      name: "A couple of questions",
    });

    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("sends the answers", async () => {
    signedIn();
    let sent: unknown = null;
    watching([STEP, QUESTIONS], run({ status: "awaiting_answers" }));
    server.use(
      http.post(
        `/api/v1/runs/${RUN}/answers`,
        async ({ request: incoming }) => {
          sent = await incoming.json();
          return HttpResponse.json(run({ status: "queued" }));
        },
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await userEvent.type(
      await screen.findByLabelText("How often do you water it?"),
      "every other day",
    );
    await userEvent.click(screen.getByRole("button", { name: "Carry on" }));

    // `species: null` is always present: one shape for the server to read rather than two,
    // and null is the honest value when there was nothing to choose between.
    await waitFor(() =>
      expect(sent).toEqual({
        answers: { watering: "every other day" },
        species: null,
      }),
    );
  });

  it("says so when the run is no longer waiting", async () => {
    signedIn();
    watching([STEP, QUESTIONS], run({ status: "awaiting_answers" }));
    server.use(
      http.post(`/api/v1/runs/${RUN}/answers`, () =>
        HttpResponse.json(
          {
            type: PROBLEM.conflict,
            title: "That is no longer possible",
            status: 409,
            detail:
              "this run is running, so there is nothing waiting to be answered",
          },
          { status: 409 },
        ),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Carry on" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /nothing waiting/,
    );
  });
});

describe("the result", () => {
  it("moves focus to it when it arrives", async () => {
    // The result replaces the reasoning panel in place, after a wait long enough that
    // somebody will have gone elsewhere. Arriving without focus means the thing they waited
    // for is announced nowhere.
    signedIn();
    watching(
      [STEP, COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    const heading = await screen.findByRole("heading", {
      name: "What this looks like",
    });

    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("ranks the candidates rather than naming one", async () => {
    signedIn();
    watching(
      [STEP, COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.length).toBeGreaterThan(0);
    const names = screen
      .getAllByText(/Overwatering|Underwatering/)
      .map((n) => n.textContent);
    expect(names[0]).toBe("Overwatering");
    expect(names).toContain("Underwatering");
  });

  it("shows what argues each way", async () => {
    signedIn();
    watching(
      [COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText("Soil is wet a week after watering"),
    ).toBeInTheDocument();
    expect(screen.getByText("No smell of rot")).toBeInTheDocument();
  });

  it("shows the quick check that would tell them apart", async () => {
    signedIn();
    watching(
      [COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(await screen.findByText(/Lift the pot/)).toBeInTheDocument();
  });

  it("gives the severity in words", async () => {
    signedIn();
    watching(
      [COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(await screen.findByText("Act this week")).toBeInTheDocument();
  });

  it("leads to the plant it produced", async () => {
    signedIn();
    watching(
      [COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByRole("link", { name: "Open this plant" }),
    ).toHaveAttribute("href", `/plants/${PLANT}`);
  });
});

describe("a run that produced nothing", () => {
  it("says why, without calling it a failure", async () => {
    signedIn();
    watching(
      [
        'id: 1\nevent: completed\ndata: {"diagnosis_id":null,"plant_id":null,"rejected":true,"reason":"This looks like a doorknob, not a plant."}\n\n',
      ],
      run({ status: "completed" }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(await screen.findByText(/doorknob/)).toBeInTheDocument();
    expect(
      screen.queryByText(/could not be finished/i),
    ).not.toBeInTheDocument();
  });
});

describe("a run that failed", () => {
  it("says so and offers another", async () => {
    signedIn();
    watching(
      [
        'id: 1\nevent: failed\ndata: {"detail":"The run could not be completed."}\n\n',
      ],
      run({ status: "failed", error: "The run could not be completed." }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText(/could not be finished/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Diagnose another" }),
    ).toBeInTheDocument();
  });
});

describe("stopping a run", () => {
  it("does not stop one in a single click", async () => {
    signedIn();
    let stopped = false;
    watching([STEP]);
    server.use(
      http.delete(`/api/v1/runs/${RUN}`, () => {
        stopped = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Stop this diagnosis" }),
    );

    expect(stopped).toBe(false);
  });

  it("says that stopping does not undo what was already paid for", async () => {
    // "Cancel" reads as "undo". This one is not: the step already running finishes, and it
    // has already cost money.
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Stop this diagnosis" }),
    );

    expect(screen.getByText(/is not undone/)).toBeInTheDocument();
    expect(
      screen.getByText(/still counts towards your monthly allowance/),
    ).toBeInTheDocument();
  });

  it("stops it once confirmed", async () => {
    signedIn();
    let stopped = false;
    watching([STEP]);
    server.use(
      http.delete(`/api/v1/runs/${RUN}`, () => {
        stopped = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Stop this diagnosis" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Stop it" }));

    await waitFor(() => expect(stopped).toBe(true));
  });

  it("reports a cancelled run as stopped", async () => {
    signedIn();
    watching(
      ["id: 1\nevent: cancelled\ndata: {}\n\n"],
      run({ status: "cancelled" }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText(/This diagnosis was stopped/),
    ).toBeInTheDocument();
  });
});

describe("coming back to a run", () => {
  it("shows a run that finished while nobody was watching", async () => {
    // Opened fresh: the stream replays from the beginning and ends immediately.
    signedIn();
    watching(
      [COMPLETED],
      run({ status: "completed", diagnosis_id: DIAGNOSIS, plant_id: PLANT }),
    );
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () =>
        HttpResponse.json(DETAIL),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText(/lower leaves are yellowing/),
    ).toBeInTheDocument();
  });

  it("shows a run that failed while nobody was watching", async () => {
    signedIn();
    watching(
      [],
      run({ status: "failed", error: "The run could not be completed." }),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText(/could not be finished/i),
    ).toBeInTheDocument();
  });

  it("shows the steps so far for a run still working", async () => {
    signedIn();
    watching([STEP]);

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(
      await screen.findByText("Checking the photographs"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Stop this diagnosis" }),
    ).toBeInTheDocument();
  });

  it("puts the run in the address so a reload finds it", async () => {
    signedIn();
    server.use(
      http.post("/api/v1/runs", () => HttpResponse.json(run())),
      http.get(`/api/v1/runs/${RUN}`, () => HttpResponse.json(run())),
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(streamOf(STEP), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    render(<AppRoutes />, { route: "/diagnose" });
    await userEvent.upload(
      await screen.findByLabelText("Upload images"),
      new File(["png"], "leaf.png", { type: "image/png" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Start the diagnosis" }),
    );

    expect(
      await screen.findByText("Checking the photographs"),
    ).toBeInTheDocument();
  });
});
