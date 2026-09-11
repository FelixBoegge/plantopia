/**
 * What this plant will be recorded as, when there is nothing left to choose between.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IdentifiedAs } from "@/screens/wizard/IdentifiedAs";

describe("saying what this will be recorded as", () => {
  it("names the plant and the scientific name beside it", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Basil",
          scientific_name: "Ocimum basilicum",
          confidence: 0.85,
          method: "vision",
          vision_confidence: null,
          plantnet_confidence: null,
        }}
      />,
    );

    expect(screen.getByText("Basil")).toBeInTheDocument();
    expect(screen.getByText("(Ocimum basilicum)")).toBeInTheDocument();
  });

  it("says how it was reached and how sure that is", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Basil",
          scientific_name: "Ocimum basilicum",
          confidence: 0.85,
          method: "vision",
          vision_confidence: null,
          plantnet_confidence: null,
        }}
      />,
    );

    expect(
      screen.getByText("Read from your photo, very confident"),
    ).toBeInTheDocument();
  });

  it("gives what somebody typed no confidence at all", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Kitchen basil",
          scientific_name: null,
          confidence: 1,
          method: "typed",
          vision_confidence: null,
          plantnet_confidence: null,
        }}
      />,
    );

    expect(screen.getByText("What you told us")).toBeInTheDocument();
    expect(screen.queryByText(/What you told us, /)).not.toBeInTheDocument();
  });

  it("credits Pl@ntNet when its data is on screen", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Basil",
          scientific_name: "Ocimum basilicum",
          confidence: 0.7,
          method: "plantnet",
          vision_confidence: null,
          plantnet_confidence: null,
        }}
      />,
    );

    expect(screen.getByText(/powered by Pl@ntNet/i)).toBeInTheDocument();
  });

  it("does not credit it for a vision-only or typed candidate", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Basil",
          scientific_name: "Ocimum basilicum",
          confidence: 0.85,
          method: "vision",
          vision_confidence: null,
          plantnet_confidence: null,
        }}
      />,
    );

    expect(screen.queryByText(/Pl@ntNet/i)).not.toBeInTheDocument();
  });

  it("shows each method's own confidence for an agreed candidate", () => {
    render(
      <IdentifiedAs
        candidate={{
          common_name: "Basil",
          scientific_name: "Ocimum basilicum",
          confidence: 0.9,
          method: "agreed",
          vision_confidence: 0.85,
          plantnet_confidence: 0.65,
        }}
      />,
    );

    expect(
      screen.getByText(
        "Your photo and Pl@ntNet's database independently agree, very confident from your photo, fairly confident from Pl@ntNet",
      ),
    ).toBeInTheDocument();
  });
});
