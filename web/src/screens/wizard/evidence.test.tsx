/**
 * What a result says about how it was reached, and what it cost.
 *
 * Both were recorded from the first diagnosis and shown nowhere (`U23`). The retired
 * Streamlit page had a "Sources consulted" expander and a cost badge at the foot of every
 * result; the React migration carried neither across, and nobody had decided against them.
 *
 * The cost is only worth showing as of `U26`: until that was fixed the diagnosis record
 * held the finishing pass of an interrupted run alone, so a badge would have displayed a
 * figure about 17% too low.
 */

import { render, screen, within } from "@/test/render";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DiagnosisDetail } from "@/api/types";
import { Differential } from "@/screens/wizard/Differential";

const DIAGNOSIS = {
  id: "01a0-diagnosis",
  plant_id: "01a0-basil",
  observation_id: "01a0-observation",
  is_healthy: false,
  reasoning: "The soil is wet and the lower leaves are yellowing.",
  candidates: [
    {
      disorder_id: "overwatering",
      name: "Overwatering",
      probability: 0.6,
      severity: "act_this_week",
      supporting_evidence: ["wet soil"],
      contradicting_evidence: [],
      distinguishing_test: "Feel the soil three days after watering.",
    },
  ],
  species_method: null,
  progress_verdict: null,
  species_confirmed: false,
  weather: null,
  created_at: "2026-03-02T12:00:00Z",
  cost_usd: null,
  token_usage: null,
  sources: [],
};

function detail(overrides: Partial<DiagnosisDetail["diagnosis"]> = {}) {
  return {
    diagnosis: { ...DIAGNOSIS, ...overrides },
    roadmap_steps: [],
  } as unknown as DiagnosisDetail;
}

const CONSULTED = /reference material consulted/i;

/** The `<details>` the summary belongs to. `getByRole("group")` is not a reliable mapping
 *  for `<details>` in jsdom, so the element is reached through its summary text. */
function disclosure(): HTMLDetailsElement {
  const summary = screen.getByText(CONSULTED);
  const found = summary.closest("details");
  if (!found)
    throw new Error("the consulted-material summary is not inside a <details>");
  return found as HTMLDetailsElement;
}

describe("what the diagnosis consulted", () => {
  const SOURCES = [
    {
      name: "Overwatering",
      section: "Symptoms",
      origin: "knowledge_base" as const,
    },
    {
      name: "Root rot",
      section: "Look-alikes and how to tell them apart",
      origin: "knowledge_base" as const,
    },
    {
      name: "rhs.org.uk",
      section: "Caring for Calathea",
      origin: "web" as const,
    },
  ];

  it("lists every passage, named and sectioned", async () => {
    render(<Differential detail={detail({ sources: SOURCES })} />);
    const list = within(disclosure()).getByRole("list");

    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getByText(/Overwatering/)).toBeInTheDocument();
    expect(
      within(list).getByText(/Look-alikes and how to tell them apart/),
    ).toBeInTheDocument();
  });

  it("starts closed, and opens when asked", async () => {
    // A disclosure rather than a list always open: the differential is the answer, and
    // eighteen passages above the treatment plan would bury it. `<details>` because it is
    // the element for this, and it works before any JavaScript runs.
    render(<Differential detail={detail({ sources: SOURCES })} />);

    expect(disclosure().open).toBe(false);
    await userEvent.click(screen.getByText(CONSULTED));
    expect(disclosure().open).toBe(true);
  });

  it("says which came from the web rather than the knowledge base", async () => {
    // The distinction a reader most needs: a corpus section was written for this project
    // and curated, a web result was found. `M4` is why it is provenance and not a score.
    render(<Differential detail={detail({ sources: SOURCES })} />);
    const list = within(disclosure()).getByRole("list");

    expect(within(list).getAllByText(/knowledge base/i)).toHaveLength(2);
    expect(within(list).getByText(/^web$/i)).toBeInTheDocument();
  });

  it("counts them on the summary, so the size is visible before opening", async () => {
    render(<Differential detail={detail({ sources: SOURCES })} />);

    expect(screen.getByText(CONSULTED)).toHaveTextContent("3");
  });

  it("shows no score, because two score scales share that list", async () => {
    render(<Differential detail={detail({ sources: SOURCES })} />);

    expect(
      within(disclosure()).queryByText(/0\.6|60%/),
    ).not.toBeInTheDocument();
  });

  it("is absent entirely when a diagnosis recorded none", () => {
    // Every diagnosis reached before these were carried. A heading over an empty list
    // reads as a failure rather than as an absence.
    render(<Differential detail={detail({ sources: [] })} />);

    expect(screen.queryByText(CONSULTED)).not.toBeInTheDocument();
  });
});

describe("what the diagnosis cost", () => {
  const USAGE = {
    prompt_tokens: 11482,
    completion_tokens: 1464,
    total_tokens: 12946,
  };

  it("shows the tokens and the price together", () => {
    render(
      <Differential
        detail={detail({ cost_usd: 0.0293021, token_usage: USAGE })}
      />,
    );

    const badge = screen.getByText(/12,946 tokens/);

    expect(badge).toHaveTextContent("$0.0293");
  });

  it("shows nothing at all when nothing was measured", () => {
    // `M18`: a failed run records no cost. "$0.0000" would say it ran and was free.
    render(
      <Differential detail={detail({ cost_usd: null, token_usage: null })} />,
    );

    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("shows the tokens when only the price is missing", () => {
    // The provider reports usage and cost separately, and `core/cost.py` keeps a null cost
    // rather than inventing a zero when only the price is absent.
    render(
      <Differential detail={detail({ cost_usd: null, token_usage: USAGE })} />,
    );

    expect(screen.getByText(/12,946 tokens/)).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });
});
