/**
 * The activity list.
 *
 * What a step called and how long it took are optional for good: every step recorded before
 * they existed is replayed to a client on reconnect without them, so the list has to render
 * a step that carries neither.
 */

import { describe, expect, it } from "vitest";

import { Reasoning } from "@/screens/wizard/Reasoning";
import { render, screen } from "@/test/render";

const STEP = {
  sequence: 1,
  id: "identifying",
  description: "Identifying the species",
};

describe("the activity list", () => {
  it("names what a step called", async () => {
    render(
      <Reasoning
        steps={[{ ...STEP, calls: "acme/see-1 via OpenRouter" }]}
        working={false}
        connected
      />,
    );

    expect(
      await screen.findByText(/acme\/see-1 via OpenRouter/),
    ).toBeInTheDocument();
  });

  it("says how long a step took, in seconds", async () => {
    render(
      <Reasoning
        steps={[{ ...STEP, duration_ms: 4120 }]}
        working={false}
        connected
      />,
    );

    expect(await screen.findByText(/took 4\.1s/)).toBeInTheDocument();
  });

  it("renders a step that carries neither", async () => {
    render(<Reasoning steps={[STEP]} working={false} connected />);

    expect(
      await screen.findByText("Identifying the species"),
    ).toBeInTheDocument();
  });

  it("keeps announcing itself", async () => {
    // The only way somebody who cannot see the screen knows a ninety-second run is alive.
    const { container } = render(<Reasoning steps={[STEP]} working connected />);

    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
  });
});
