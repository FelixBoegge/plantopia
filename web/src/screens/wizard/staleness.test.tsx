import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import type { Question } from "@/api/types";
import { Questions } from "@/screens/wizard/Questions";
import { ageInDays, Staleness } from "@/screens/wizard/Staleness";
import { render } from "@/test/render";

const TODAY = new Date("2026-08-31T09:00:00");

function dateQuestion(prefill: string): Question {
  return {
    key: "captured_at",
    text: "When was this photograph taken?",
    kind: "date",
    options: [],
    prefill,
    prefill_note: "Recorded by your camera",
    required: true,
  };
}

/** The warning, on its own, at the three ages that decide it. */
describe("how old is too old", () => {
  it("says nothing about a photograph within the threshold", () => {
    render(<Staleness captured="2026-08-28" threshold={7} today={TODAY} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing at exactly the threshold", () => {
    // Seven days old with a threshold of seven is not *older than* seven. The boundary is
    // where an off-by-one would live, and warning here would nag everybody who uploads a
    // week-old photograph the moment it turns a week old.
    render(<Staleness captured="2026-08-24" threshold={7} today={TODAY} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("speaks up a day past the threshold", () => {
    render(<Staleness captured="2026-08-23" threshold={7} today={TODAY} />);

    expect(screen.getByRole("status")).toHaveTextContent("8 days old");
  });

  it("asks for a fresher photograph rather than refusing this one", () => {
    // Somebody whose plant died last week and who has only last week's photograph is
    // exactly who needs an answer.
    render(<Staleness captured="2026-08-01" threshold={7} today={TODAY} />);

    expect(screen.getByRole("status")).toHaveTextContent(/upload one taken today/i);
    expect(screen.getByRole("status")).not.toHaveTextContent(/cannot|refuse/i);
  });

  it("says nothing when the run did not send a threshold", () => {
    render(<Staleness captured="2026-01-01" threshold={null} today={TODAY} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing about a date it cannot read", () => {
    render(<Staleness captured="not a date" threshold={7} today={TODAY} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says nothing about a date in the future", () => {
    // A camera clock set wrong, or somebody mid-keystroke. Neither is a stale photograph.
    render(<Staleness captured="2026-12-01" threshold={7} today={TODAY} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("counts whole days regardless of the time of day", () => {
    expect(ageInDays("2026-08-24", new Date("2026-08-31T23:59:00"))).toBe(7);
    expect(ageInDays("2026-08-24", new Date("2026-08-31T00:01:00"))).toBe(7);
  });
});

/** And in place, following the field rather than the metadata. */
describe("the warning at the pause", () => {
  // `Staleness` defaults to the real clock, which is right in the application and rots in a
  // test: every date below would drift past the threshold on its own as the months pass,
  // and the suite would start failing for a reason that has nothing to do with the code.
  beforeAll(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(TODAY);
  });
  afterAll(() => {
    vi.useRealTimers();
  });

  function pause(prefill: string) {
    return render(
      <Questions
        questions={[dateQuestion(prefill)]}
        identification={null}
        staleAfterDays={7}
        onAnswer={() => {}}
        busy={false}
        failure={null}
      />,
    );
  }

  it("appears for a photograph whose prefilled date is old", () => {
    pause("2026-08-01");

    expect(screen.getByRole("status")).toHaveTextContent(/less reliable/i);
  });

  it("goes away when the owner corrects the date to a recent one", async () => {
    // The whole reason this watches the field: the date is prefilled from the camera and
    // the owner may know better. A warning that ignored the correction would be arguing
    // with them about a fact they had just supplied.
    pause("2026-08-01");
    expect(screen.getByRole("status")).toBeInTheDocument();

    const field = screen.getByLabelText(/when was this photograph taken/i);
    await userEvent.clear(field);
    await userEvent.type(field, "2026-08-30");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("appears when the owner corrects a recent date to an old one", async () => {
    pause("2026-08-30");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    const field = screen.getByLabelText(/when was this photograph taken/i);
    await userEvent.clear(field);
    await userEvent.type(field, "2026-06-01");

    expect(screen.getByRole("status")).toHaveTextContent(/less reliable/i);
  });

  it("does not stop the run being carried on", async () => {
    // A caution, not a gate.
    let sent = false;
    render(
      <Questions
        questions={[dateQuestion("2026-08-01")]}
        identification={null}
        staleAfterDays={7}
        onAnswer={() => {
          sent = true;
        }}
        busy={false}
        failure={null}
      />,
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /carry on/i }));

    expect(sent).toBe(true);
  });
});
