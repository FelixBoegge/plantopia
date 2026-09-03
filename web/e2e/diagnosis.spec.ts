import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { signUp } from "./people";

/**
 * A diagnosis, from an upload through the pause to a rendered differential.
 *
 * The wizard is the hardest thing here to test and the most valuable to get right: a run
 * takes about a minute and a half, streams its progress, stops halfway to ask questions, and
 * resumes. Every one of those is invisible to a mocked API, and two of them have been
 * broken here in ways a green suite reported as working.
 */

const PHOTOGRAPH = resolve(import.meta.dirname, "../../test_pics/20260810_105048.jpg");

test("runs a diagnosis through the questions to a differential", async ({ page }) => {
  await signUp(page, "diagnosis");

  // Scoped to the header: the empty plants screen offers the same link, and a test that
  // clicked "whichever" would silently stop covering the header the day the empty state
  // changed.
  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  // More than one step, and each arriving on its own rather than all at the end — which is
  // the difference between a stream and a page that waited.
  await expect(page.getByText("Checking the photographs")).toBeVisible();
  await expect(page.getByText("Identifying the species")).toBeVisible();
  const stepsBeforeThePause = await page.getByRole("listitem").count();
  expect(stepsBeforeThePause).toBeGreaterThan(1);

  // The interrupt. The graph stops inside a node and waits; nothing about the connection
  // says so, which is why the run's state has to.
  await expect(page.getByRole("heading", { name: "A couple of questions" })).toBeVisible();
  await expect(page.getByLabel(/How often do you water/)).toBeVisible();

  // Focus is here, not wherever the last step left it.
  await expect(page.getByRole("heading", { name: "A couple of questions" })).toBeFocused();

  await page.getByLabel(/How often do you water/).fill("About twice a week");
  await page.getByLabel(/drainage holes/i).selectOption({ index: 1 });
  await page.getByLabel(/How much light/).selectOption({ index: 1 });
  await page.getByRole("button", { name: "Carry on" }).click();

  // The steps already shown survive the resume rather than being replaced by a fresh list.
  await expect(page.getByText("Checking the photographs")).toBeVisible();
  await expect(page.getByText("Weighing the evidence")).toBeVisible();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("Overwatering")).toBeVisible();
  await expect(page.getByText("Nitrogen deficiency")).toBeVisible();

  // Severity in words, never in colour alone.
  await expect(page.getByText("Act this week")).toBeVisible();

  // And the plan, which is the half somebody actually does something with.
  await expect(page.getByText(/Stop watering until/)).toBeVisible();
});

test("shows the finished diagnosis on the plant it created", async ({ page }) => {
  // The run creates the plant when it was not given one, and which plant that was is
  // something the client cannot work out for itself — it used to have to guess by
  // timestamp.
  await signUp(page, "created");

  // Scoped to the header: the empty plants screen offers the same link, and a test that
  // clicked "whichever" would silently stop covering the header the day the empty state
  // changed.
  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Every other day");
  await page.getByLabel(/drainage holes/i).selectOption({ index: 0 });
  await page.getByLabel(/How much light/).selectOption({ index: 0 });
  await page.getByRole("button", { name: "Carry on" }).click();

  await page.getByRole("heading", { name: "What this looks like" }).waitFor({
    timeout: 60_000,
  });

  await page.getByRole("link", { name: "Plantopia" }).click();

  // Named by what it turned out to be, because nobody was asked to name it. The scripted
  // vision model says "Basil"; the chosen candidate is what lands on the card.
  await expect(page.getByText("Basil").first()).toBeVisible();

  await page.getByText("Basil").first().click();

  // The detail screen summarises rather than repeating the differential: what the agent
  // concluded, how urgent it is, and the plan — with the ranking one link away.
  await expect(page.getByText(/points at the roots/)).toBeVisible();
  await expect(page.getByText("Act this week")).toBeVisible();
  await expect(page.getByText(/Stop watering until/)).toBeVisible();
  await expect(page.getByRole("link", { name: "See the full differential" })).toBeVisible();
});

test("asks which plant it is when the methods disagree, and takes the answer", async ({
  page,
}) => {
  // The scripted vision model says "Basil"; the scripted second opinion returns "Thai
  // basil" leading "Holy basil". Only the leading answer is ever offered — one vote per
  // method — so "Holy basil" never reaches the screen. A disagreement between the two
  // methods that remain is the case the choice screen exists for, and the one the browser
  // walks through.
  await signUp(page, "chooses");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await expect(page.getByRole("heading", { name: "Which plant is this?" })).toBeVisible({
    timeout: 60_000,
  });

  // How each answer was reached, in words, and the credit its terms require.
  await expect(page.getByText("Read from your photo")).toBeVisible();
  // One, not two: the specialist's response carried two candidates and only the leading
  // one is offered, which is what stopped this screen showing three rows with two of them
  // reading identically.
  await expect(page.getByText(/Matched against a plant database/)).toHaveCount(1);
  await expect(page.getByText("Holy basil")).toHaveCount(0);
  await expect(page.getByText(/powered by Pl@ntNet/i)).toBeVisible();

  // Confidence in words, never as a bare number.
  await expect(page.getByText(/confident|guess/).first()).toBeVisible();
  await expect(page.getByText(/0\.71|0\.85/)).toHaveCount(0);

  // Overriding the leader with the specialist's answer.
  await page.getByRole("radio", { name: /Thai basil/ }).check();
  await page.getByLabel(/How often do you water/).fill("Twice a week");
  await page.getByRole("button", { name: "Carry on" }).click();

  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible({
    timeout: 60_000,
  });
});

test("carries a typed species through to the choice", async ({ page }) => {
  await signUp(page, "typed");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("Do you know what it is?").fill("Ocimum tenuiflorum");
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await expect(page.getByRole("heading", { name: "Which plant is this?" })).toBeVisible({
    timeout: 60_000,
  });

  // What the owner said leads, and both methods still ran and are still offered — which is
  // the difference between leading and deciding.
  await expect(page.getByText("What you told us")).toBeVisible();
  await expect(page.getByRole("radio").first()).toBeChecked();
  await expect(page.getByText("Read from your photo")).toBeVisible();
});

test("a plant's history reads as one sequence", async ({ page }) => {
  // Everything the timeline shows was already stored and already fetched by this page; what
  // is worth driving a browser through is that it arrives in one order and that a diagnosis
  // is reachable from the event that produced it.
  await signUp(page, "history");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Every other day");
  await page.getByRole("button", { name: "Carry on" }).click();
  await page
    .getByRole("heading", { name: "What this looks like" })
    .waitFor({ timeout: 60_000 });

  await page.getByRole("link", { name: "Plantopia" }).click();
  await page.getByText("Basil").first().click();

  const history = page.getByRole("region", { name: "Plant history" });
  await expect(history).toBeVisible();

  // The photograph carries a real capture date, so the observation is dated by when it was
  // taken rather than by when it was uploaded — and says nothing about uploads.
  //
  // Asserted on the machine-readable attribute rather than the rendered text: the date is
  // formatted in the viewer's locale, so the visible string is "August 10, 2026" in this
  // browser and "10 August 2026" under the component tests. A test that pinned one of those
  // would be pinning where it happened to run.
  await expect(history.locator('time[datetime^="2026-08-10"]')).toBeVisible();
  await expect(history.getByText(/date the photograph was uploaded/)).toHaveCount(0);

  // The diagnosis is on the timeline and reachable from it. Named differently from the
  // current-verdict link above so the two are not two identical links to one page.
  await expect(history.getByRole("link", { name: "See this diagnosis" })).toBeVisible();
  await history.getByRole("link", { name: "See this diagnosis" }).click();
  await expect(page.getByRole("heading", { name: "What this looks like" })).toBeVisible();
});

test("an outdoor plant's weather is readable without seeing the chart", async ({ page }) => {
  // The chart is decorative by construction; the table beside it is what carries the values.
  // A browser is where that distinction is worth checking, because it is the one place the
  // real DOM and the real styles are both present.
  await signUp(page, "history-weather");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Upload images").setInputFiles(PHOTOGRAPH);
  await page.getByRole("radio", { name: "Outdoors" }).check();
  await page.getByRole("button", { name: "Start the diagnosis" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Every other day");
  await page.getByLabel(/Which town or city/).fill("Berlin");
  await page.getByRole("button", { name: "Carry on" }).click();
  await page
    .getByRole("heading", { name: "What this looks like" })
    .waitFor({ timeout: 60_000 });

  await page.getByRole("link", { name: "Plantopia" }).click();
  await page.getByText("Basil").first().click();

  const history = page.getByRole("region", { name: "Plant history" });
  const table = history.getByRole("table");
  await expect(table).toBeAttached();

  // The scripted weather puts a frost on a known date. Read out of the table rather than
  // off the chart, which is exactly the point.
  await expect(table).toContainText("-2 °C");
  await expect(history.getByText(/frost on/)).toBeVisible();
});
