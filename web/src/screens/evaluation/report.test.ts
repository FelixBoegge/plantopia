/**
 * Reading a harness result into something a page can render.
 *
 * The API hands this file through untouched — `services/evaluations.py` parses JSON and
 * returns the object — so the shape is the harness's, not a schema's. Every reader here
 * therefore returns `null` for a section it cannot find rather than throwing, and the page
 * omits that section. A harness that grows a field is then a page that ignores it, and a
 * harness that drops one is a page missing a panel, neither of which is a blank screen.
 *
 * The fixture is the real 2026-08-19 result, trimmed to three categories and three cases.
 * Written from the file rather than by hand because the last hand-written one used `top_1`
 * and `top_3`, which the harness has never emitted — it writes `top1` and `top3`, and the
 * page it was testing passed only because it iterated whatever keys it was given.
 */

import { describe, expect, it } from "vitest";

import FIXTURE from "./fixture.json";
import { readReport } from "@/screens/evaluation/report";

const report = () => readReport(FIXTURE as Record<string, unknown>);

describe("accuracy", () => {
  it("reads the two rates and the two counts apart", () => {
    // The bug this replaces: the page mapped over every key in `accuracy` and multiplied
    // each by 100, so `scored: 28` rendered as "2800%" and `failed: 0` as "0%" — a count
    // presented as a proportion, beside `by_category` rendered as "[object Object]".
    const found = report().accuracy;

    expect(found?.top1).toBeCloseTo(0.892857, 5);
    expect(found?.top3).toBeCloseTo(0.964285, 5);
    expect(found?.scored).toBe(28);
    expect(found?.failed).toBe(0);
  });

  it("counts how many cases the top-1 rate stands for", () => {
    // A rate over 28 cases is a different claim from the same rate over 3, and the count
    // is what makes it readable as evidence rather than as a score.
    expect(report().accuracy?.top1Cases).toBe(25);
  });

  it("orders the categories weakest first", () => {
    // What a maintainer opens this to find. Alphabetical order buries it.
    expect(report().accuracy?.byCategory.map((c) => c.name)).toEqual([
      "other",
      "light",
      "pest",
    ]);
  });

  it("keeps each category's case count", () => {
    // 50% of two cases and 100% of five are not comparable, and nothing on the page can
    // say so without the denominator.
    const other = report().accuracy?.byCategory.find((c) => c.name === "other");

    expect(other?.scored).toBe(2);
    expect(other?.top1).toBe(0.5);
  });
});

describe("the Ragas metrics", () => {
  it("reads all four, with their coverage", () => {
    const names = report().metrics.map((m) => m.label);

    expect(names).toContain("Faithfulness");
    expect(names).toContain("Answer relevancy");
    expect(names).toContain("Context precision");
    expect(names).toContain("Context recall");
  });

  it("carries how many cases each one actually scored", () => {
    // `M22`: context precision timed out on every row of an earlier run and scored 0 of 28
    // while the other three scored all of them. A metric's value means nothing without
    // knowing whether it was measured, so the coverage travels with it.
    const precision = report().metrics.find(
      (m) => m.key === "context_precision",
    );

    expect(precision?.scored).toBe(28);
    expect(precision?.total).toBe(28);
  });

  it("explains what each one measures", () => {
    // A reader who does not already know what "context precision" is cannot act on 54%.
    for (const metric of report().metrics) {
      expect(metric.meaning.length).toBeGreaterThan(20);
    }
  });

  it("says which one is scored over a narrower set than the others", () => {
    // `M22` again, and the reason the four are not quite comparable: context precision is
    // computed over the similarity-ranked passages only, while the rest see everything the
    // model read.
    const precision = report().metrics.find(
      (m) => m.key === "context_precision",
    );
    const faithfulness = report().metrics.find((m) => m.key === "faithfulness");

    expect(precision?.caveat).toBeTruthy();
    expect(faithfulness?.caveat).toBeNull();
  });
});

describe("stability", () => {
  it("reads the three rates and says which way is better", () => {
    // Two of the three are better when lower, which no amount of colour conveys on its
    // own. Carried as data so the page states it in words.
    const found = report().stability;

    expect(found?.measures).toEqual([
      expect.objectContaining({
        label: "Top-1 agreement",
        higherIsBetter: true,
      }),
      expect.objectContaining({
        label: "Candidate churn",
        higherIsBetter: false,
      }),
      expect.objectContaining({
        label: "Question drift",
        higherIsBetter: false,
      }),
    ]);
  });

  it("reads what the rates were measured over", () => {
    expect(report().stability?.cases).toBe(8);
    expect(report().stability?.runsPerCase).toBe(5);
  });
});

describe("the cases", () => {
  it("says whether each one was hit at rank one and within three", () => {
    const first = report().cases[0]!;

    expect(first.id).toBe("aphids-clustered-new-growth-hibiscus");
    expect(first.groundTruth).toBe("aphids");
    expect(first.top1Hit).toBe(true);
    expect(first.top3Hit).toBe(true);
  });

  it("reads a miss as a miss rather than as an absence", () => {
    const missed = readReport({
      cases: [
        {
          case_id: "x",
          ground_truth: "root-rot",
          category: "watering",
          candidates: ["overwatering", "poor-drainage"],
          questions_asked: [],
          error: null,
        },
      ],
    }).cases[0]!;

    expect(missed.top1Hit).toBe(false);
    expect(missed.top3Hit).toBe(false);
  });

  it("counts a truth found below rank one as a top-three hit", () => {
    const near = readReport({
      cases: [
        {
          case_id: "x",
          ground_truth: "root-rot",
          category: "watering",
          candidates: ["overwatering", "root-rot"],
          questions_asked: [],
          error: null,
        },
      ],
    }).cases[0]!;

    expect(near.top1Hit).toBe(false);
    expect(near.top3Hit).toBe(true);
  });

  it("carries a case that failed outright", () => {
    const broken = readReport({
      cases: [
        {
          case_id: "x",
          ground_truth: "root-rot",
          category: "watering",
          candidates: [],
          questions_asked: [],
          error: "the provider dropped the connection",
        },
      ],
    }).cases[0]!;

    expect(broken.error).toBe("the provider dropped the connection");
    expect(broken.top1Hit).toBe(false);
  });
});

describe("provenance", () => {
  it("reads what produced the numbers", () => {
    const found = report().provenance;

    expect(found?.reasoningModel).toBe("openai/gpt-4o");
    expect(found?.embeddingModel).toBe("openai/text-embedding-3-small");
    expect(found?.goldenSetSize).toBe(28);
    expect(found?.costUsd).toBeCloseTo(1.5443525, 6);
    expect(found?.totalTokens).toBe(449445);
  });
});

describe("a result this page does not recognise", () => {
  it("reads an empty object as nothing rather than throwing", () => {
    const empty = readReport({});

    expect(empty.accuracy).toBeNull();
    expect(empty.provenance).toBeNull();
    expect(empty.stability).toBeNull();
    expect(empty.metrics).toEqual([]);
    expect(empty.cases).toEqual([]);
  });

  it("ignores a section whose shape is wrong", () => {
    // The API passes the harness's file through untouched, so this is the honest failure
    // mode: a section that changed shape is dropped, not rendered as debris.
    const odd = readReport({ accuracy: "unexpectedly a string", ragas: 42 });

    expect(odd.accuracy).toBeNull();
    expect(odd.metrics).toEqual([]);
  });

  it("reads accuracy without its category breakdown", () => {
    const partial = readReport({
      accuracy: { top1: 0.5, top3: 0.75, scored: 4, failed: 0 },
    });

    expect(partial.accuracy?.top1).toBe(0.5);
    expect(partial.accuracy?.byCategory).toEqual([]);
  });
});
