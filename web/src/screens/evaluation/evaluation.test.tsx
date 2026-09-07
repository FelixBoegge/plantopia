/**
 * The report page.
 *
 * It used to show four tiles built by multiplying every value in `accuracy` by a hundred,
 * and a `<details>` holding the rest of the file as JSON. So `scored: 28` read as "2800%",
 * `failed: 0` as "0%", `by_category` as "[object Object]" — and everything the harness
 * actually measures, the four Ragas metrics included, was only readable as raw JSON.
 *
 * The fixture is the real 2026-08-19 result, trimmed. The test it replaces used `top_1` and
 * `top_3`, which the harness has never written.
 */

import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/routes/routes";
import FIXTURE from "@/screens/evaluation/fixture.json";
import { render, screen, within } from "@/test/render";
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
  may_read_evaluations: true,
};

function showing(results: unknown, generatedAt = "2026-08-19T10:51:29Z") {
  server.use(
    http.post("/api/v1/auth/refresh", () =>
      HttpResponse.json({ access_token: "fresh" }),
    ),
    http.get("/api/v1/me", () => HttpResponse.json(ACCOUNT)),
    http.get("/api/v1/evaluation/latest", () =>
      HttpResponse.json({ generated_at: generatedAt, results }),
    ),
  );
}

const open = () => render(<AppRoutes />, { route: "/admin/evaluation" });

describe("the report's headline", () => {
  it("leads with the rank-one rate and how many cases it stands for", async () => {
    showing(FIXTURE);
    open();

    expect(await screen.findByText("89.3%")).toBeInTheDocument();
    expect(
      screen.getByText(/25 of 28 cases led with the right disorder/),
    ).toBeInTheDocument();
  });

  it("shows counts as counts, not as percentages", async () => {
    // The bug this page was rebuilt for: `scored: 28` rendered as "2800%" and `failed: 0`
    // as "0%", because every value under `accuracy` was multiplied by a hundred.
    showing(FIXTURE);
    open();
    await screen.findByText("89.3%");

    expect(screen.queryByText("2800%")).not.toBeInTheDocument();
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.getByText(/none failed to run/)).toBeInTheDocument();
  });

  it("never renders a nested section as an object", async () => {
    // `by_category` used to land in the same loop and stringify.
    showing(FIXTURE);
    open();
    await screen.findByText("89.3%");

    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  });
});

describe("the four Ragas metrics", () => {
  it("shows every one, with its value", async () => {
    showing(FIXTURE);
    open();

    expect(await screen.findByText("Faithfulness")).toBeInTheDocument();
    expect(screen.getByText("Answer relevancy")).toBeInTheDocument();
    expect(screen.getByText("Context precision")).toBeInTheDocument();
    expect(screen.getByText("Context recall")).toBeInTheDocument();
    expect(screen.getByText("74.4%")).toBeInTheDocument();
    expect(screen.getByText("98.2%")).toBeInTheDocument();
  });

  it("says what each one measures", async () => {
    // A reader who does not already know what context precision is cannot act on 54.5%.
    showing(FIXTURE);
    open();

    expect(
      await screen.findByText(
        /fraction of the retrieved material was relevant/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/hallucination check/)).toBeInTheDocument();
  });

  it("says how many cases each one was scored on", async () => {
    // `M22`: an earlier run had this metric time out on every row and score 0 of 28 while
    // the other three scored all of them. A value without its denominator cannot be told
    // apart from that.
    showing(FIXTURE);
    open();
    await screen.findByText("Faithfulness");

    expect(screen.getAllByText(/Scored on 28 of 28 cases/).length).toBe(4);
  });

  it("flags the one measured over a narrower set", async () => {
    showing(FIXTURE);
    open();

    expect(
      await screen.findByText(/similarity-ranked passages only/),
    ).toBeInTheDocument();
  });
});

describe("accuracy by category", () => {
  it("lists the categories weakest first", async () => {
    showing(FIXTURE);
    open();
    await screen.findByText(/By category, weakest first/);

    const names = screen
      .getAllByRole("term")
      .map((term) => term.textContent?.trim())
      .filter((name) => ["other", "light", "pest"].includes(name ?? ""));

    expect(names).toEqual(["other", "light", "pest"]);
  });

  it("gives each category its case count, so a rate can be weighed", async () => {
    // 50% of two cases and 100% of five are not comparable claims.
    showing(FIXTURE);
    open();

    expect(await screen.findByText(/top-3 50% · 2 cases/)).toBeInTheDocument();
  });
});

describe("stability", () => {
  it("says which way is better for each measure", async () => {
    // Two of the three read better when lower, and no colour can carry that.
    showing(FIXTURE);
    open();
    await screen.findByText("Candidate churn");

    expect(screen.getByText(/Higher is better/)).toBeInTheDocument();
    expect(screen.getAllByText(/Lower is better/).length).toBe(2);
  });

  it("says what the measures were run over", async () => {
    showing(FIXTURE);
    open();

    expect(
      await screen.findByText(/running 8 cases 5 times each/),
    ).toBeInTheDocument();
  });
});

describe("the case list", () => {
  it("replaces the JSON dump with a table", async () => {
    showing(FIXTURE);
    open();

    expect(
      await screen.findByRole("columnheader", { name: "Should have said" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Everything measured")).not.toBeInTheDocument();
  });

  it("says what became of each case in words", async () => {
    showing(FIXTURE);
    open();
    const table = await screen.findByRole("table");

    expect(
      within(table).getByText("aphids-clustered-new-growth-hibiscus"),
    ).toBeInTheDocument();
    expect(
      within(table).getAllByText("Correct at rank one").length,
    ).toBeGreaterThan(0);
  });
});

describe("provenance", () => {
  it("says what produced the numbers", async () => {
    showing(FIXTURE);
    open();

    expect(await screen.findByText("openai/gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("449,445")).toBeInTheDocument();
    expect(screen.getByText("$1.54")).toBeInTheDocument();
  });
});

describe("a result the page does not recognise", () => {
  it("shows what it can and omits the rest, rather than breaking", async () => {
    // The API hands the harness's file through untouched, so this is the real failure mode.
    showing({ accuracy: { top1: 0.5, top3: 0.75, scored: 4, failed: 1 } });
    open();

    expect(await screen.findByText("50%")).toBeInTheDocument();
    expect(screen.getByText(/1 could not be scored/)).toBeInTheDocument();
    expect(screen.queryByText("Faithfulness")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("keeps its heading when there is nothing it can read at all", async () => {
    showing({ something: "the harness has never written" });
    open();

    expect(
      await screen.findByRole("heading", { name: "RAG Evaluation Report" }),
    ).toBeInTheDocument();
  });
});
