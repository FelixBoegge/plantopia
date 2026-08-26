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

test("runs a check through the questions to a differential", async ({ page }) => {
  await signUp(page, "diagnosis");

  // Scoped to the header: the empty plants screen offers the same link, and a test that
  // clicked "whichever" would silently stop covering the header the day the empty state
  // changed.
  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Photographs").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("What is it called?").fill("Kitchen basil");
  await page.getByRole("button", { name: "Start the check" }).click();

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
  await page.getByLabel("Photographs").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("What is it called?").fill("Windowsill basil");
  await page.getByRole("button", { name: "Start the check" }).click();

  await page.getByLabel(/How often do you water/).waitFor({ timeout: 60_000 });
  await page.getByLabel(/How often do you water/).fill("Every other day");
  await page.getByLabel(/drainage holes/i).selectOption({ index: 0 });
  await page.getByLabel(/How much light/).selectOption({ index: 0 });
  await page.getByRole("button", { name: "Carry on" }).click();

  await page.getByRole("heading", { name: "What this looks like" }).waitFor({
    timeout: 60_000,
  });

  await page.getByRole("link", { name: "Plantopia" }).click();
  await expect(page.getByText("Windowsill basil")).toBeVisible();

  await page.getByText("Windowsill basil").click();
  await expect(page.getByRole("heading", { name: "Windowsill basil" })).toBeVisible();

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
  // The scripted vision model says "Basil"; the scripted second opinion says "Thai basil"
  // and "Holy basil". A disagreement is the case the choice screen exists for, so it is the
  // one the browser walks through.
  await signUp(page, "chooses");

  await page.getByRole("navigation").getByRole("link", { name: "Diagnose a plant" }).click();
  await page.getByLabel("Photographs").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("What is it called?").fill("Disputed basil");
  await page.getByRole("button", { name: "Start the check" }).click();

  await expect(page.getByRole("heading", { name: "Which plant is this?" })).toBeVisible({
    timeout: 60_000,
  });

  // How each answer was reached, in words, and the credit its terms require.
  await expect(page.getByText("Read from your photo")).toBeVisible();
  // Two, because the specialist returned two candidates and each says where it came from.
  await expect(page.getByText(/Matched against a plant database/)).toHaveCount(2);
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
  await page.getByLabel("Photographs").setInputFiles(PHOTOGRAPH);
  await page.getByLabel("What is it called?").fill("My herb");
  await page.getByLabel("Do you know what it is?").fill("Ocimum tenuiflorum");
  await page.getByRole("button", { name: "Start the check" }).click();

  await expect(page.getByRole("heading", { name: "Which plant is this?" })).toBeVisible({
    timeout: 60_000,
  });

  // What the owner said leads, and both methods still ran and are still offered — which is
  // the difference between leading and deciding.
  await expect(page.getByText("What you told us")).toBeVisible();
  await expect(page.getByRole("radio").first()).toBeChecked();
  await expect(page.getByText("Read from your photo")).toBeVisible();
});
