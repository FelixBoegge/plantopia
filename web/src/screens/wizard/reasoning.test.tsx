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
    const { container } = render(
      <Reasoning steps={[STEP]} working connected />,
    );

    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
  });
});

describe("the line that says it is still working", () => {
  /** The steps are the substance; this line is only liveness. A single model call can take
   *  a minute, and for that minute the list does not change — which reads as a stall. */

  it("says Processing while a step is in flight", () => {
    render(<Reasoning steps={[STEP]} working connected />);

    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("turns a spinner beside it", () => {
    render(<Reasoning steps={[STEP]} working connected />);

    const spinner = screen.getByTestId("processing-spinner");

    expect(spinner).toBeInTheDocument();
    expect(spinner.className).toContain("animate-spin");
  });

  it("hides the spinner from assistive technology", () => {
    // The text beside it already carries the meaning, inside a live region that announces
    // it. A spinner given a name of its own is announced a second time, saying nothing.
    render(<Reasoning steps={[STEP]} working connected />);

    expect(screen.getByTestId("processing-spinner")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("stops animating for somebody who asked motion to stop", () => {
    // `motion-reduce:animate-none` rather than hiding it: a still ring says "there is
    // something here and it has not finished", which is the whole message.
    render(<Reasoning steps={[STEP]} working connected />);

    expect(screen.getByTestId("processing-spinner").className).toContain(
      "motion-reduce:animate-none",
    );
  });

  it("says Reconnecting instead when the stream has dropped", () => {
    // A different fact, worth keeping distinct: the run is still going, and the page has
    // lost contact with it. The spinner stays, because both states are "still working".
    render(<Reasoning steps={[STEP]} working connected={false} />);

    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
    expect(screen.getByTestId("processing-spinner")).toBeInTheDocument();
  });

  it("is absent once nothing is in flight", () => {
    render(<Reasoning steps={[STEP]} working={false} connected />);

    expect(screen.queryByText("Processing")).not.toBeInTheDocument();
    expect(screen.queryByTestId("processing-spinner")).not.toBeInTheDocument();
  });
});
