/**
 * Severity, and the reason it never travels as a colour alone.
 *
 * About one man in twelve cannot reliably separate the red and green these badges use. A
 * diagnosis whose seriousness is carried by hue is one they cannot read.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Severity, severityText } from "@/components/Severity";

describe("a severity", () => {
  it.each([
    ["monitor", "Keep an eye on it"],
    ["act_this_week", "Act this week"],
    ["act_today", "Act today"],
  ])("renders %s as words", (value, words) => {
    render(<Severity severity={value} />);

    expect(screen.getByText(words)).toBeInTheDocument();
  });

  it("never puts a database value on the screen", () => {
    // `act_this_week` is a stored value. A fallback that rendered it raw would be a
    // fallback that leaks one on exactly the day somebody adds a fourth severity.
    render(<Severity severity="something_new_and_unmapped" />);

    expect(
      screen.queryByText(/something_new_and_unmapped/),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Unrated")).toBeInTheDocument();
  });

  it("shows nothing at all when there is no severity", () => {
    const { container } = render(<Severity severity={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders a healthy plant as its own green badge, not a severity", () => {
    // A healthy differential carries no candidates at all — there is no severity to
    // fall back to, only silence, which read as nothing having been found rather than
    // as a good result.
    render(<Severity severity={null} healthy />);

    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("prefers healthy over a severity if somehow both are given", () => {
    render(<Severity severity="act_today" healthy />);

    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.queryByText("Act today")).not.toBeInTheDocument();
  });

  it("offers the same words for a sentence", () => {
    expect(severityText("act_today")).toBe("Act today");
    expect(severityText(null)).toBeNull();
  });
});

describe("everywhere else", () => {
  it("is the only place a severity is turned into something readable", async () => {
    // The words live in one table so that a fourth severity is one edit. A screen that
    // wrote its own would keep rendering the old three and silently miss the new one —
    // which is exactly the kind of thing a passing suite would not notice.
    const { readdirSync, readFileSync } = await import("node:fs");
    const { join } = await import("node:path");

    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (
          /\.tsx?$/.test(entry.name) &&
          !/\.test\.tsx?$/.test(entry.name)
        ) {
          if (path.includes("Severity")) continue;
          const source = readFileSync(path, "utf8");
          // A severity's stored values, appearing anywhere but the component that maps them.
          if (/["']act_(today|this_week)["']|["']monitor["']/.test(source)) {
            offenders.push(path);
          }
        }
      }
    };
    walk("src");

    expect(offenders).toEqual([]);
  });
});
