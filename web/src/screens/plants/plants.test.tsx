/**
 * The plants somebody owns, and one of them in detail.
 *
 * The state usually left out is the third one: a load that failed. An empty grid shown
 * because a request failed is a screen telling somebody their plants are gone.
 */

import { HttpResponse, http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PROBLEM } from "@/api/problems";
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
  runs_used: 0,
  runs_allowed: 20,
  allowance_resets_at: "2026-04-01T00:00:00Z",
};

const BASIL = {
  id: "01a0-basil",
  name: "Kitchen basil",
  species: "Ocimum basilicum",
  species_confidence: 0.9,
  location_kind: "indoor" as const,
  location_text: null,
  photo_ref: "01a0-photo",
  created_at: "2026-03-01T12:00:00Z",
};

const DIAGNOSIS = {
  id: "01a0-diagnosis",
  plant_id: BASIL.id,
  observation_id: "01a0-observation",
  is_healthy: false,
  reasoning: "The lower leaves are yellowing from the base upward.",
  candidates: [
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
};

const STEP = {
  id: "01a0-step",
  diagnosis_id: DIAGNOSIS.id,
  ordinal: 1,
  action: "Stop watering until the top 3cm are dry",
  rationale: "Roots need air as much as water.",
  success_signal: "New growth stops yellowing within a fortnight.",
  tier: 1,
  due_date: "2026-03-09T12:00:00Z",
  status: "pending" as const,
  completed_at: null,
};

function signedIn() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get("/api/v1/photos/:key", () =>
      HttpResponse.arrayBuffer(new Uint8Array([137, 80, 78, 71]).buffer),
    ),
  );
}

function withPlants(summaries: unknown[]) {
  server.use(http.get("/api/v1/plants", () => HttpResponse.json(summaries)));
}

function withPlant(detail: Record<string, unknown>) {
  server.use(
    http.get(`/api/v1/plants/${BASIL.id}`, () => HttpResponse.json(detail)),
  );
}

const DETAIL = {
  plant: BASIL,
  observations: [],
  diagnoses: [DIAGNOSIS],
  roadmap_steps: [STEP],
  feedback_due: false,
};

describe("the plant grid", () => {
  it("lists what somebody owns", async () => {
    signedIn();
    withPlants([
      { plant: BASIL, latest_diagnosis: DIAGNOSIS, pending_step_count: 2 },
    ]);

    render(<AppRoutes />, { route: "/" });

    expect(await screen.findByText("Kitchen basil")).toBeInTheDocument();
    expect(screen.getByText("Ocimum basilicum")).toBeInTheDocument();
  });

  it("says how urgent each one is, in words", async () => {
    signedIn();
    withPlants([
      { plant: BASIL, latest_diagnosis: DIAGNOSIS, pending_step_count: 2 },
    ]);

    render(<AppRoutes />, { route: "/" });

    expect(await screen.findByText("Act this week")).toBeInTheDocument();
  });

  it("says how much is left to do", async () => {
    signedIn();
    withPlants([
      { plant: BASIL, latest_diagnosis: DIAGNOSIS, pending_step_count: 2 },
    ]);

    render(<AppRoutes />, { route: "/" });

    expect(await screen.findByText("2 steps to do")).toBeInTheDocument();
  });

  it("invites a first diagnosis when there is nothing yet", async () => {
    signedIn();
    withPlants([]);

    render(<AppRoutes />, { route: "/" });

    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Diagnose your first plant" }),
    ).toBeInTheDocument();
  });

  it("says so when the plants could not be loaded", async () => {
    // Rather than an empty grid, which says somebody's plants are gone.
    signedIn();
    server.use(
      http.get("/api/v1/plants", () =>
        HttpResponse.json(
          { type: PROBLEM.internal, title: "Internal error", status: 500 },
          { status: 500 },
        ),
      ),
    );

    render(<AppRoutes />, { route: "/" });

    expect(
      await screen.findByText(
        "Your plants could not be loaded",
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nothing here yet.")).not.toBeInTheDocument();
  });
});

describe("photographs", () => {
  it("are fetched with the session rather than linked to", async () => {
    // An `<img src>` cannot send an Authorization header, and the usual workaround puts the
    // token in the query string — where it lands in the access log and in the Referer of
    // whatever the page loads next.
    signedIn();
    let authorised: string | null = null;
    server.use(
      http.get("/api/v1/photos/:key", ({ request: incoming }) => {
        authorised = incoming.headers.get("Authorization");
        return HttpResponse.arrayBuffer(
          new Uint8Array([137, 80, 78, 71]).buffer,
        );
      }),
    );
    withPlants([
      { plant: BASIL, latest_diagnosis: null, pending_step_count: 0 },
    ]);

    render(<AppRoutes />, { route: "/" });
    await screen.findByText("Kitchen basil");

    await waitFor(() => expect(authorised).toBe("Bearer fresh"));
  });

  it("never appear in a URL with a credential in it", async () => {
    signedIn();
    withPlants([
      { plant: BASIL, latest_diagnosis: null, pending_step_count: 0 },
    ]);

    render(<AppRoutes />, { route: "/" });
    await screen.findByText("Kitchen basil");

    await waitFor(() => {
      const images = Array.from(document.querySelectorAll("img"));
      expect(images.length).toBeGreaterThan(0);
      for (const image of images) {
        expect(image.src).not.toContain("fresh");
        expect(image.src.startsWith("blob:")).toBe(true);
      }
    });
  });
});

describe("one plant", () => {
  it("shows what Plantopia thinks", async () => {
    signedIn();
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });

    expect(
      await screen.findByText(
        "The lower leaves are yellowing from the base upward.",
      ),
    ).toBeInTheDocument();
  });

  it("says so when nothing has been diagnosed yet", async () => {
    signedIn();
    withPlant({ ...DETAIL, diagnoses: [], roadmap_steps: [] });

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });

    expect(
      await screen.findByText(/Nothing has been diagnosed yet/i),
    ).toBeInTheDocument();
  });

  it("offers checking it again", async () => {
    signedIn();
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });

    expect(
      await screen.findByRole("link", { name: "Check again" }),
    ).toHaveAttribute("href", `/plants/${BASIL.id}/diagnose`);
  });
});

describe("the plan", () => {
  it("shows each step with why it is there and what success looks like", async () => {
    signedIn();
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });

    expect(await screen.findByText(STEP.action)).toBeInTheDocument();
    expect(screen.getByText(STEP.rationale)).toBeInTheDocument();
    expect(screen.getByText(/New growth stops yellowing/)).toBeInTheDocument();
  });

  it("marks a step done", async () => {
    signedIn();
    let marked: unknown = null;
    let done = false;
    server.use(
      http.patch(
        `/api/v1/roadmap-steps/${STEP.id}`,
        async ({ request: incoming }) => {
          marked = await incoming.json();
          done = true;
          return new HttpResponse(null, { status: 204 });
        },
      ),
      http.get(`/api/v1/plants/${BASIL.id}`, () =>
        HttpResponse.json({
          ...DETAIL,
          roadmap_steps: [
            done
              ? {
                  ...STEP,
                  status: "done",
                  completed_at: "2026-03-05T12:00:00Z",
                }
              : STEP,
          ],
        }),
      ),
    );

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: STEP.action }),
    );

    expect(marked).toEqual({ status: "done" });
  });

  it("shows the change without a manual reload", async () => {
    // The count on the grid comes from the same rows. A checkbox that only changed itself
    // would leave the two disagreeing.
    signedIn();
    let done = false;
    server.use(
      http.patch(`/api/v1/roadmap-steps/${STEP.id}`, () => {
        done = true;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(`/api/v1/plants/${BASIL.id}`, () =>
        HttpResponse.json({
          ...DETAIL,
          roadmap_steps: [
            done
              ? {
                  ...STEP,
                  status: "done",
                  completed_at: "2026-03-05T12:00:00Z",
                }
              : STEP,
          ],
        }),
      ),
    );

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: STEP.action }),
    );

    expect(await screen.findByText(/^Done /)).toBeInTheDocument();
  });

  it("reopens a step, clearing its completion", async () => {
    // A step marked done and then reopened has not been done, and a date saying otherwise
    // is a lie the history repeats.
    signedIn();
    let sent: unknown = null;
    server.use(
      http.patch(
        `/api/v1/roadmap-steps/${STEP.id}`,
        async ({ request: incoming }) => {
          sent = await incoming.json();
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );
    withPlant({
      ...DETAIL,
      roadmap_steps: [
        { ...STEP, status: "done", completed_at: "2026-03-05T12:00:00Z" },
      ],
    });

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: STEP.action }),
    );

    expect(sent).toEqual({ status: "pending" });
  });
});

describe("renaming and removing", () => {
  it("renames a plant", async () => {
    signedIn();
    let sent: unknown = null;
    server.use(
      http.patch(
        `/api/v1/plants/${BASIL.id}`,
        async ({ request: incoming }) => {
          sent = await incoming.json();
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    const field = await screen.findByLabelText("Name");
    await userEvent.clear(field);
    await userEvent.type(field, "Windowsill basil");
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));

    expect(sent).toEqual({ name: "Windowsill basil" });
  });

  it("does not remove a plant in one click", async () => {
    // A plant carries its whole history — every diagnosis, photograph and conversation.
    signedIn();
    let removed = false;
    server.use(
      http.delete(`/api/v1/plants/${BASIL.id}`, () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove this plant" }),
    );

    expect(removed).toBe(false);
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be undone/i);
  });

  it("removes it once confirmed", async () => {
    signedIn();
    let removed = false;
    server.use(
      http.delete(`/api/v1/plants/${BASIL.id}`, () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    withPlant(DETAIL);
    withPlants([]);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove this plant" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Yes, remove it" }),
    );

    await waitFor(() => expect(removed).toBe(true));
  });

  it("lets somebody change their mind", async () => {
    signedIn();
    withPlant(DETAIL);

    render(<AppRoutes />, { route: `/plants/${BASIL.id}` });
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove this plant" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));

    expect(
      screen.getByRole("button", { name: "Remove this plant" }),
    ).toBeInTheDocument();
  });
});
