/**
 * What produced a finished diagnosis.
 *
 * The same steps the sidebar showed while the run was happening, read back afterwards. The
 * case worth protecting is the empty one: every diagnosis made before any of this was
 * recorded has no activity, and a heading over nothing reads as something having broken.
 */

import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/routes/routes";
import { render, screen, waitFor } from "@/test/render";
import { server } from "@/test/server";

const DIAGNOSIS = "01a0-diagnosis";
const PLANT = "01a0-plant";

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
        probability: 0.62,
        severity: "act_this_week",
        supporting_evidence: ["Soil pulls away from the pot"],
        contradicting_evidence: [],
        distinguishing_test: "Water thoroughly and watch overnight.",
      },
    ],
    created_at: "2026-03-01T12:00:00Z",
    cost_usd: null,
    token_usage: null,
    sources: [],
  },
  roadmap_steps: [],
};

function signedIn() {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get(`/api/v1/diagnoses/${DIAGNOSIS}`, () => HttpResponse.json(DETAIL)),
  );
}

describe("how a finished diagnosis was reached", () => {
  it("lists the steps it took", async () => {
    signedIn();
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json([
          {
            sequence: 1,
            step: "identifying",
            description: "Identifying the species",
            calls: "acme/see-1 via OpenRouter",
            duration_ms: 4120,
            occurred_at: "2026-03-01T12:00:00Z",
          },
        ]),
      ),
    );

    render(<AppRoutes />, { route: `/diagnoses/${DIAGNOSIS}` });

    expect(
      await screen.findByText("Identifying the species"),
    ).toBeInTheDocument();
    expect(screen.getByText(/acme\/see-1 via OpenRouter/)).toBeInTheDocument();
    expect(screen.getByText(/took 4\.1s/)).toBeInTheDocument();
  });

  it("says nothing about a step the endpoint reports as null", async () => {
    // The stream omits both fields on an older step; the endpoint sends them as null, since
    // that is what an absent optional serialises to. A check for `undefined` alone passes
    // the first and fails the second, and the failure is silent: `null / 1000` is 0, so
    // every step on every older diagnosis claimed to have taken 0.0s.
    signedIn();
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json([
          {
            sequence: 1,
            step: "identifying",
            description: "Identifying the species",
            calls: null,
            duration_ms: null,
            occurred_at: "2026-03-01T12:00:00Z",
          },
        ]),
      ),
    );

    render(<AppRoutes />, { route: `/diagnoses/${DIAGNOSIS}` });
    await screen.findByText("Identifying the species");

    expect(screen.queryByText(/took/)).not.toBeInTheDocument();
  });

  it("shows one line where two nodes share a sentence", async () => {
    // `guard_input` and `quality_check` are both "Checking the photographs", because the
    // distinction is internal. The live stream already collapses consecutive repeats; the
    // record has to agree, or the same run reads as twelve steps while it runs and thirteen
    // afterwards.
    signedIn();
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json([
          {
            sequence: 1,
            step: "checking",
            description: "Checking the photographs",
            occurred_at: "2026-03-01T12:00:00Z",
          },
          {
            sequence: 2,
            step: "checking",
            description: "Checking the photographs",
            occurred_at: "2026-03-01T12:00:01Z",
          },
          {
            sequence: 3,
            step: "identifying",
            description: "Identifying the species",
            occurred_at: "2026-03-01T12:00:02Z",
          },
        ]),
      ),
    );

    render(<AppRoutes />, { route: `/diagnoses/${DIAGNOSIS}` });
    await screen.findByText("Identifying the species");

    expect(screen.getAllByText("Checking the photographs")).toHaveLength(1);
  });

  it("says nothing at all when nothing was recorded", async () => {
    signedIn();
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json([]),
      ),
    );

    render(<AppRoutes />, { route: `/diagnoses/${DIAGNOSIS}` });
    await screen.findByText("Underwatering");

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "How this was reached" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("still shows the diagnosis when the activity cannot be loaded", async () => {
    // A panel is not worth losing the result over.
    signedIn();
    server.use(
      http.get(`/api/v1/diagnoses/${DIAGNOSIS}/activity`, () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );

    render(<AppRoutes />, { route: `/diagnoses/${DIAGNOSIS}` });

    expect(await screen.findByText("Underwatering")).toBeInTheDocument();
  });
});
