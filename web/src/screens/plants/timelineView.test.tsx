import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type {
  Diagnosis,
  Message,
  Observation,
  RoadmapStep,
  WeatherSummary,
} from "@/api/types";
import { Timeline } from "@/screens/plants/Timeline";
import { Weather, summarise } from "@/screens/plants/Weather";
import { render } from "@/test/render";

function observation(overrides: Partial<Observation> = {}): Observation {
  return {
    id: "obs-1",
    plant_id: "plant-1",
    kind: "initial",
    photo_refs: [],
    user_notes: null,
    created_at: "2026-08-20T09:00:00Z",
    captured_at: null,
    latitude: null,
    longitude: null,
    weather: null,
    ...overrides,
  };
}

function diagnosis(overrides: Partial<Diagnosis> = {}): Diagnosis {
  return {
    id: "diag-1",
    plant_id: "plant-1",
    observation_id: "obs-1",
    is_healthy: false,
    reasoning: "Yellowing consistent with overwatering.",
    candidates: [
      {
        disorder_id: "overwatering",
        name: "Overwatering",
        probability: 0.7,
        severity: "act_this_week",
        supporting_evidence: [],
        contradicting_evidence: [],
        distinguishing_test: "Unpot and look at the roots",
      },
    ],
    species_method: null,
    progress_verdict: null,
    species_confirmed: false,
    weather: null,
    created_at: "2026-08-20T10:00:00Z",
    cost_usd: null,
    ...overrides,
  };
}

function step(overrides: Partial<RoadmapStep> = {}): RoadmapStep {
  return {
    id: "step-1",
    diagnosis_id: "diag-1",
    ordinal: 1,
    action: "Let the top third dry out",
    rationale: "Reduces root saturation",
    success_signal: "New growth firms up",
    tier: 1,
    due_date: "2026-08-25T00:00:00Z",
    status: "pending",
    completed_at: null,
    ...overrides,
  };
}

const SERIES: WeatherSummary = {
  min_temp_c: -2,
  max_temp_c: 34,
  total_precip_mm: 6.5,
  frost_days: 1,
  heat_days: 1,
  days_covered: 3,
  days: [
    { on: "2026-08-17", min_temp_c: -2, max_temp_c: 12, precip_mm: 0 },
    { on: "2026-08-18", min_temp_c: 9, max_temp_c: 34, precip_mm: 1.5 },
    { on: "2026-08-19", min_temp_c: 11, max_temp_c: 21, precip_mm: 5 },
  ],
  forecast: [
    { on: "2026-08-21", min_temp_c: 10, max_temp_c: 20, precip_mm: 0 },
  ],
};

function timeline(props: Partial<Parameters<typeof Timeline>[0]> = {}) {
  return render(
    <Timeline observations={[]} diagnoses={[]} steps={[]} {...props} />,
  );
}

describe("the history section", () => {
  it("carries a heading", () => {
    timeline({ observations: [observation()] });

    expect(
      screen.getByRole("heading", { name: /plant history/i }),
    ).toBeInTheDocument();
  });

  it("says so plainly when there is no history", () => {
    timeline();

    expect(
      screen.getByText(/nothing has happened to this plant yet/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows a diagnosis by its leading candidate, and links to the full one", () => {
    timeline({ diagnoses: [diagnosis()] });

    expect(screen.getByText("Overwatering")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /see this diagnosis/i }),
    ).toHaveAttribute("href", "/diagnoses/diag-1");
  });

  it("says when nothing was wrong", () => {
    timeline({ diagnoses: [diagnosis({ is_healthy: true, candidates: [] })] });

    expect(screen.getByText(/nothing wrong was found/i)).toBeInTheDocument();
  });

  it("puts the newest event first", () => {
    timeline({
      observations: [
        observation({ id: "obs-1", captured_at: "2026-08-01T00:00:00Z" }),
      ],
      diagnoses: [diagnosis({ created_at: "2026-08-20T00:00:00Z" })],
    });

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]!).getByText("Overwatering")).toBeInTheDocument();
  });

  it("shows a settled step and leaves a pending one to the plan", () => {
    timeline({
      steps: [
        step({
          id: "done",
          status: "done",
          completed_at: "2026-08-26T00:00:00Z",
        }),
        step({ id: "pending", action: "Repot into fresh compost" }),
      ],
    });

    expect(screen.getByText("Let the top third dry out")).toBeInTheDocument();
    expect(
      screen.queryByText("Repot into fresh compost"),
    ).not.toBeInTheDocument();
  });

  it("distinguishes a skipped step from a done one", () => {
    timeline({
      steps: [
        step({ status: "skipped", completed_at: "2026-08-26T00:00:00Z" }),
      ],
    });

    expect(screen.getByText("Skipped")).toBeInTheDocument();
  });
});

describe("dating an event", () => {
  it("uses the capture date without comment", () => {
    // The visible text is formatted in the viewer's locale, so it is asserted through the
    // datetime attribute rather than by matching one locale's rendering.
    const { container } = timeline({
      observations: [observation({ captured_at: "2026-08-10T10:50:00Z" })],
    });

    expect(
      container.querySelector('time[datetime="2026-08-10T10:50:00Z"]'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/uploaded/i)).not.toBeInTheDocument();
  });

  it("says so when it only has the upload date", () => {
    // Presenting an upload date as a capture date would be the timeline claiming something
    // the photograph never declared.
    timeline({ observations: [observation({ captured_at: null })] });

    expect(
      screen.getByText(/date the photograph was uploaded/i),
    ).toBeInTheDocument();
  });

  it("shows the date to a person as well", () => {
    const { container } = timeline({
      observations: [observation({ captured_at: "2026-08-10T10:50:00Z" })],
    });

    // Whatever the locale renders, it is not the raw instant.
    const shown = container.querySelector("time")?.textContent ?? "";
    expect(shown).not.toBe("2026-08-10T10:50:00Z");
    expect(shown).toMatch(/2026/);
  });
});

describe("an escalation", () => {
  const escalated: Message[] = [
    {
      id: "msg-1",
      plant_id: "plant-1",
      role: "assistant",
      content: "Flagged.",
      tool_calls: [
        {
          name: "suggest_new_diagnosis",
          args: { reason: "Black spots that the last diagnosis did not cover" },
          result: "",
        },
      ],
      created_at: "2026-08-22T10:00:00Z",
    },
  ];

  it("appears with its reason", () => {
    timeline({ observations: [observation()], messages: escalated });

    expect(screen.getByText(/flagged for a fresh look/i)).toBeInTheDocument();
    expect(screen.getByText(/black spots/i)).toBeInTheDocument();
  });

  it("is absent while the transcript has not loaded", () => {
    timeline({ observations: [observation()] });

    expect(
      screen.queryByText(/flagged for a fresh look/i),
    ).not.toBeInTheDocument();
    // And the rest of the timeline rendered anyway rather than waiting for it.
    expect(screen.getByRole("listitem")).toBeInTheDocument();
  });
});

describe("the weather", () => {
  it("is read from the table rather than the chart", () => {
    // The chart is decorative by construction; the table is what carries the values to
    // anybody who cannot see it, which the web-client spec requires.
    render(<Weather summary={SERIES} />);

    const table = screen.getByRole("table");
    expect(
      within(table).getByRole("rowheader", { name: "2026-08-17" }),
    ).toBeInTheDocument();
    expect(within(table).getByText("-2 °C")).toBeInTheDocument();
    expect(within(table).getByText("5 mm")).toBeInTheDocument();
  });

  it("draws one point per day inside a viewBox", () => {
    const { container } = render(<Weather summary={SERIES} />);

    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox");
    // Two temperature paths, and one bar per day.
    expect(container.querySelectorAll("path")).toHaveLength(2);
    expect(container.querySelectorAll("rect")).toHaveLength(SERIES.days.length);
  });

  it("hides the chart from assistive technology, since the table says the same", () => {
    const { container } = render(<Weather summary={SERIES} />);

    expect(container.querySelector("svg")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("does not draw the forecast", () => {
    // Seven days ahead of the run, which is the past by the time anybody reads a history.
    render(<Weather summary={SERIES} />);

    expect(screen.queryByText("2026-08-21")).not.toBeInTheDocument();
  });

  it("appears against the observation that carries it", () => {
    timeline({ observations: [observation({ weather: SERIES })] });

    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows nothing at all for an observation with none", () => {
    timeline({ observations: [observation({ weather: null })] });

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(document.querySelector("svg")).toBeNull();
  });

  it("shows nothing for a summary stored before the series was kept", () => {
    timeline({
      observations: [observation({ weather: { ...SERIES, days: [] } })],
    });

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("the weather in a sentence", () => {
  it("names the range and the notable days", () => {
    const said = summarise(SERIES);

    expect(said).toContain("3 days to 2026-08-19");
    expect(said).toContain("frost on 2026-08-17");
    expect(said).toContain("above 32 °C on 2026-08-18");
    expect(said).toContain("6.5 mm of rain");
  });

  it("says nothing about frost or heat in an unremarkable window", () => {
    const said = summarise({
      ...SERIES,
      days: [
        { on: "2026-08-17", min_temp_c: 11, max_temp_c: 19, precip_mm: 1 },
        { on: "2026-08-18", min_temp_c: 12, max_temp_c: 20, precip_mm: 0 },
      ],
    });

    expect(said).not.toContain("frost");
    expect(said).not.toContain("above");
    expect(said).toContain("11 to 20 °C");
  });
});

describe("enlarging a photograph", () => {
  it("offers each thumbnail as a control rather than a picture", async () => {
    timeline({ observations: [observation({ photo_refs: ["photo-1"] })] });

    expect(
      await screen.findByRole("button", { name: "Enlarge photograph 1" }),
    ).toBeInTheDocument();
  });

  it("opens the photograph over the page", async () => {
    timeline({ observations: [observation({ photo_refs: ["photo-1"] })] });
    await userEvent.click(
      await screen.findByRole("button", { name: "Enlarge photograph 1" }),
    );

    expect(
      screen.getByRole("dialog", { name: "Photograph" }),
    ).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    timeline({ observations: [observation({ photo_refs: ["photo-1"] })] });
    await userEvent.click(
      await screen.findByRole("button", { name: "Enlarge photograph 1" }),
    );

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when the backdrop is clicked", async () => {
    timeline({ observations: [observation({ photo_refs: ["photo-1"] })] });
    await userEvent.click(
      await screen.findByRole("button", { name: "Enlarge photograph 1" }),
    );

    await userEvent.click(screen.getByRole("dialog", { name: "Photograph" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("puts the keyboard inside what just appeared", async () => {
    timeline({ observations: [observation({ photo_refs: ["photo-1"] })] });
    await userEvent.click(
      await screen.findByRole("button", { name: "Enlarge photograph 1" }),
    );

    expect(
      screen.getByRole("button", { name: "Close the photograph" }),
    ).toHaveFocus();
  });
});

describe("a diagnosis and its photographs as one entry", () => {
  it("draws the finding inside the observation it was made from", () => {
    // Two entries put an August photograph at the bottom of the history and the diagnosis
    // of it at the top, with another run's photographs in between.
    timeline({
      observations: [
        observation({
          id: "obs-1",
          captured_at: "2026-08-14T09:00:00Z",
          photo_refs: ["p"],
        }),
      ],
      diagnoses: [
        diagnosis({
          id: "diag-1",
          observation_id: "obs-1",
          created_at: "2026-09-03T09:00:00Z",
        }),
      ],
    });

    const [entry] = screen.getAllByRole("article");
    expect(within(entry!).getByText(/photographed/i)).toBeInTheDocument();
    expect(within(entry!).getByText("Diagnosed")).toBeInTheDocument();
    expect(
      within(entry!).getByRole("link", { name: "See this diagnosis" }),
    ).toBeInTheDocument();
  });

  it("shows the verdict with the finding", () => {
    timeline({
      observations: [observation({ id: "obs-1" })],
      diagnoses: [
        diagnosis({
          id: "diag-1",
          observation_id: "obs-1",
          progress_verdict: "improving",
        }),
      ],
    });

    expect(
      screen.getByText(/Improving since the last diagnosis/),
    ).toBeInTheDocument();
  });
});

describe("the weather chart's landmarks", () => {
  it("names the day the photographs were taken", () => {
    // Twenty-one points of line, and only one of them is the day the plant was looked at.
    render(
      <Weather
        summary={SERIES}
        capturedOn={`${SERIES.days[1]!.on}T09:00:00Z`}
      />,
    );

    expect(screen.getByText(/Photographed on/)).toBeInTheDocument();
  });

  it("says nothing about a capture date outside the window", () => {
    render(<Weather summary={SERIES} capturedOn="1999-01-01T09:00:00Z" />);

    expect(screen.queryByText(/Photographed on/)).not.toBeInTheDocument();
  });

  it("draws nothing extra when the camera said nothing", () => {
    render(<Weather summary={SERIES} />);

    expect(screen.queryByText(/Photographed on/)).not.toBeInTheDocument();
  });
});
