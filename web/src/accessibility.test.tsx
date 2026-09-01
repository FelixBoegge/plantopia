/**
 * Every screen, checked automatically, plus the things a checker cannot see.
 *
 * An automated pass catches the mechanical failures — an unlabelled control, a contrast
 * ratio, a heading level skipped — and none of the interesting ones. Focus moving to the
 * right place, content arriving without a navigation being announced, and severity never
 * travelling as colour alone are judgements, and they are tested individually below.
 *
 * The rule this file enforces is that nothing regresses silently. A violation here is a
 * failure, not a warning, because a warning in a test suite is a thing people learn to
 * scroll past.
 */

import { HttpResponse, http } from "msw";
import { axe } from "vitest-axe";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const PLANT = "01a0-basil";
const RUN = "01a0-run";

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

const DETAIL = {
  plant: {
    id: PLANT,
    name: "Kitchen basil",
    species: "Ocimum basilicum",
    species_confidence: 0.9,
    location_kind: "indoor" as const,
    location_text: null,
    photo_ref: null,
    created_at: "2026-03-01T12:00:00Z",
  },
  // Carrying a weather series deliberately. An empty list would render an empty timeline,
  // and axe would pass over a plant page without ever seeing the chart, the table beside it
  // or a single timeline event — which is the shape of pass that says nothing.
  observations: [
    {
      id: "01a0-observation",
      plant_id: PLANT,
      kind: "initial" as const,
      photo_refs: [],
      user_notes: null,
      created_at: "2026-08-20T09:00:00Z",
      captured_at: "2026-08-19T10:50:00Z",
      latitude: null,
      longitude: null,
      weather: {
        min_temp_c: -2,
        max_temp_c: 21,
        total_precip_mm: 5,
        frost_days: 1,
        heat_days: 0,
        days_covered: 3,
        days: [
          { on: "2026-08-17", min_temp_c: -2, max_temp_c: 12, precip_mm: 0 },
          { on: "2026-08-18", min_temp_c: 9, max_temp_c: 19, precip_mm: 0 },
          { on: "2026-08-19", min_temp_c: 11, max_temp_c: 21, precip_mm: 5 },
        ],
        forecast: [],
      },
    },
  ],
  diagnoses: [
    {
      id: "01a0-diagnosis",
      plant_id: PLANT,
      observation_id: "01a0-observation",
      is_healthy: false,
      reasoning: "The lower leaves are yellowing.",
      candidates: [
        {
          disorder_id: "overwatering",
          name: "Overwatering",
          probability: 0.62,
          severity: "act_this_week",
          supporting_evidence: ["Soil is wet"],
          contradicting_evidence: [],
          distinguishing_test: "Lift the pot.",
        },
      ],
      created_at: "2026-03-02T12:00:00Z",
      cost_usd: 0.04,
    },
  ],
  roadmap_steps: [
    {
      id: "01a0-step",
      diagnosis_id: "01a0-diagnosis",
      ordinal: 1,
      action: "Stop watering",
      rationale: "Roots need air.",
      success_signal: "New growth recovers.",
      tier: 1,
      due_date: "2026-03-09T12:00:00Z",
      status: "pending" as const,
      completed_at: null,
    },
  ],
  feedback_due: false,
};

function everything() {
  server.use(
    http.post("/api/v1/auth/refresh", () => HttpResponse.json({ access_token: "fresh" })),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get("/api/v1/plants", () =>
      HttpResponse.json([{ plant: DETAIL.plant, latest_diagnosis: DETAIL.diagnoses[0], pending_step_count: 1 }]),
    ),
    http.get(`/api/v1/plants/${PLANT}`, () => HttpResponse.json(DETAIL)),
    http.get(`/api/v1/plants/${PLANT}/messages`, () => HttpResponse.json([])),
    http.get("/api/v1/profile/facts", () => HttpResponse.json([])),
    http.get(`/api/v1/runs/${RUN}`, () => HttpResponse.json({})),
  );
}

function signedOut() {
  server.use(
    http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 401 })),
  );
}

/** Screens reachable without a session, and the landmark each one lands on. */
const OPEN_SCREENS: [string, string, string][] = [
  ["/login", "Sign in", "heading"],
  ["/register", "Register", "heading"],
  ["/verify-email", "Verify your address", "heading"],
  ["/reset-password", "Reset your password", "heading"],
];

const SIGNED_IN_SCREENS: [string, string][] = [
  ["/", "Your plants"],
  [`/plants/${PLANT}`, "Kitchen basil"],
  ["/diagnose", "Diagnose a plant"],
  ["/account", "Your account"],
];

describe("the automated pass", () => {
  it.each(OPEN_SCREENS)("finds nothing to fix on %s", async (route, heading) => {
    signedOut();

    const { container } = render(<AppRoutes />, { route });
    await screen.findByRole("heading", { name: heading });

    expect(await axe(container)).toHaveNoViolations();
  });

  it.each(SIGNED_IN_SCREENS)("finds nothing to fix on %s", async (route, heading) => {
    everything();

    const { container } = render(<AppRoutes />, { route });
    await screen.findByRole("heading", { name: heading });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("what a checker cannot see", () => {
  it("gives every severity a written label", async () => {
    // About one man in twelve cannot reliably separate the red and green these use. A
    // checker cannot tell that a colour is carrying the meaning; only a person can.
    everything();

    render(<AppRoutes />, { route: `/plants/${PLANT}` });

    expect(await screen.findByText("Act this week")).toBeInTheDocument();
  });

  it("states a run's status in words", async () => {
    everything();
    server.use(
      http.get(`/api/v1/runs/${RUN}`, () =>
        HttpResponse.json({
          id: RUN,
          plant_id: null,
          kind: "diagnosis",
          status: "failed",
          created_at: "2026-03-01T12:00:00Z",
          finished_at: "2026-03-01T12:01:00Z",
          diagnosis_id: null,
          error: "The run could not be completed.",
        }),
      ),
      http.get(`/api/v1/runs/${RUN}/events`, () => new HttpResponse(null, { status: 204 })),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });

    expect(await screen.findByText(/could not be finished/i)).toBeInTheDocument();
  });

  it("announces the agent's progress", async () => {
    // It arrives without a navigation. Somebody who cannot see the screen has no other way
    // to know anything is happening.
    everything();
    server.use(
      http.get(`/api/v1/runs/${RUN}`, () =>
        HttpResponse.json({
          id: RUN,
          plant_id: null,
          kind: "diagnosis",
          status: "running",
          created_at: "2026-03-01T12:00:00Z",
          finished_at: null,
          diagnosis_id: null,
          error: null,
        }),
      ),
      http.get(`/api/v1/runs/${RUN}/events`, () =>
        new HttpResponse(
          new TextEncoder().encode(
            'id: 1\nevent: step\ndata: {"step":"checking","description":"Checking the photographs"}\n\n',
          ),
          { headers: { "Content-Type": "text/event-stream" } },
        ),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByText("Checking the photographs");

    const live = document.querySelector("[aria-live='polite']");
    expect(live).toBeInTheDocument();
    expect(live?.textContent).toContain("Checking the photographs");
  });

  it("announces a failure rather than merely showing it", async () => {
    signedOut();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            type: "https://plantopia.example/problems/unauthenticated",
            title: "Not signed in",
            status: 401,
            detail: "Those credentials were not accepted.",
          },
          { status: 401 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/login" });
    await userEvent.type(await screen.findByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-entirely");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    // `role="alert"` rather than a red paragraph: a form that silently grows one is a form
    // somebody using a screen reader submits twice.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("uses links for navigation so a browser can do what browsers do", async () => {
    everything();

    render(<AppRoutes />, { route: "/" });

    expect(await screen.findByRole("link", { name: "Account" })).toHaveAttribute(
      "href",
      "/account",
    );
  });

  it.each([...OPEN_SCREENS.map(([route]) => route), ...SIGNED_IN_SCREENS.map(([route]) => route)])(
    "gives %s exactly one first-level heading",
    async (route) => {
      // A screen reader's heading navigation is how many people find their way. Two h1s, or
      // none, and that stops working. Checking one screen is what let the evaluation screen
      // ship with its heading inside the branch that succeeds, so every screen is checked.
      OPEN_SCREENS.some(([open]) => open === route) ? signedOut() : everything();

      render(<AppRoutes />, { route });

      await waitFor(() =>
        expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1),
      );
    },
  );

  it("keeps a heading on a screen whose content was refused", async () => {
    // The state a member always sees. It is the failure branch, which is exactly the branch
    // a heading is most likely to be missing from.
    everything();
    server.use(
      http.get("/api/v1/evaluation/latest", () =>
        HttpResponse.json(
          {
            type: "https://plantopia.example/problems/not-found",
            title: "Not found",
            status: 404,
            detail: "No such resource.",
          },
          { status: 404 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/admin/evaluation" });
    await screen.findByText("Not available");

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("choosing between two machines", () => {
  it("finds nothing to fix in the identification chooser", async () => {
    // The one control in the application that asks somebody to arbitrate between two
    // machine judgements, which makes it the one most worth checking mechanically.
    everything();
    server.use(
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
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(new TextEncoder().encode('id: 1\nevent: questions\ndata: {"questions":[{"key":"watering","text":"How often do you water it?","kind":"text","options":[]}],"identification":[{"common_name":"Basil","scientific_name":"Ocimum basilicum","confidence":0.85,"method":"vision"},{"common_name":"Thai basil","scientific_name":"Ocimum africanum","confidence":0.71,"method":"plantnet"}]}\n\n'), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    const { container } = render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByRole("heading", { name: "Which plant is this?" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

const FRAME = 'id: 1\nevent: questions\ndata: {"questions":[{"key":"location","text":"Which town or city is the plant in?","kind":"text","options":[],"prefill":"Berlin","prefill_note":"Recorded by your camera, named by OpenStreetMap contributors","required":true},{"key":"captured_at","text":"When was the photograph taken?","kind":"date","options":[],"prefill":"2026-08-10","prefill_note":"Recorded by your camera","required":true}]}\n\n';
const EMPTY_REQUIRED = 'id: 1\nevent: questions\ndata: {"questions":[{"key":"location","text":"Which town or city is the plant in?","kind":"text","options":[],"prefill":null,"prefill_note":null,"required":true}]}\n\n';

describe("the fields a photograph filled in", () => {
  it("finds nothing to fix in a prefilled, required question", async () => {
    everything();
    server.use(
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
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(new TextEncoder().encode(FRAME), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    const { container } = render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByLabelText(/Which town or city/);

    expect(await axe(container)).toHaveNoViolations();
  });

  it("finds nothing to fix once a required field has been refused", async () => {
    // The state with an alert on screen and a field marked invalid, which is the one a
    // checker is most likely to find something in.
    everything();
    server.use(
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
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(new TextEncoder().encode(EMPTY_REQUIRED), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    const { container } = render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByLabelText(/Which town or city/);
    await userEvent.click(screen.getByRole("button", { name: "Carry on" }));
    await screen.findByRole("alert");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("announces a refusal rather than only showing it", async () => {
    everything();
    server.use(
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
      http.get(
        `/api/v1/runs/${RUN}/events`,
        () =>
          new HttpResponse(new TextEncoder().encode(EMPTY_REQUIRED), {
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );

    render(<AppRoutes />, { route: `/diagnose?run=${RUN}` });
    await screen.findByLabelText(/Which town or city/);
    await userEvent.click(screen.getByRole("button", { name: "Carry on" }));

    // `role="alert"` rather than a red paragraph, and tied to the field by
    // `aria-describedby` so it is read with the thing it is about rather than after it.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText(/Which town or city/)).toBeInvalid();
  });
});

describe("using it without a pointer", () => {
  it("reaches every control on the sign-in screen by tabbing", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/login" });
    await screen.findByLabelText("Email");

    await userEvent.tab();
    expect(screen.getByLabelText("Email")).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText("Password")).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Sign in" })).toHaveFocus();
  });

  it("reaches the consent box and the button when registering", async () => {
    signedOut();

    render(<AppRoutes />, { route: "/register" });
    await screen.findByLabelText("Email");

    await userEvent.tab();
    await userEvent.tab();
    await userEvent.tab();
    expect(screen.getByRole("checkbox")).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Create account" })).toHaveFocus();
  });

  it("can tick a plan step from the keyboard", async () => {
    everything();
    server.use(
      http.patch("/api/v1/roadmap-steps/01a0-step", () => new HttpResponse(null, { status: 204 })),
    );

    render(<AppRoutes />, { route: `/plants/${PLANT}` });
    const step = await screen.findByRole("checkbox", { name: "Stop watering" });
    step.focus();
    await userEvent.keyboard(" ");

    expect(step).toHaveFocus();
  });
});
