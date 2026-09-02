/**
 * Which way a plant is going.
 *
 * The property carrying the weight is the one about colour: this is the answer somebody is
 * least able to read from hue alone, since improving and worsening are exactly the green
 * and red pair a common form of colour blindness confuses.
 */

import { describe, expect, it } from "vitest";

import { Verdict } from "@/components/Verdict";
import { render, screen } from "@/test/render";

describe("the progress verdict", () => {
  it("says improving in words, not only in colour", () => {
    render(<Verdict verdict="improving" />);

    expect(screen.getByText(/improving/i)).toBeInTheDocument();
  });

  it("says worsening in words too", () => {
    render(<Verdict verdict="worsening" />);

    expect(screen.getByText(/worse/i)).toBeInTheDocument();
  });

  it("distinguishes a different problem from a worse one", () => {
    render(<Verdict verdict="new_problem" />);

    expect(screen.getByText(/different problem/i)).toBeInTheDocument();
  });

  it("shows nothing for a first diagnosis", () => {
    // Null means there was nothing to compare against. A label reading "unknown" would put
    // a row on screen that reports no fact.
    const { container } = render(<Verdict verdict={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows nothing for a verdict it does not recognise", () => {
    // A value the server grew and this file has not learned about is not something to put
    // in front of somebody by its own identifier.
    const { container } = render(
      <Verdict verdict={"sideways" as "improving"} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
