import { expect, test } from "@playwright/test";

import { PASSWORD, signUp } from "./people";

/**
 * Taking your data out, and closing the account.
 *
 * Both are driven through a real browser rather than only a component test because both
 * cross a boundary a mock cannot: the export arrives as bytes over an authenticated
 * request that no plain link could make, and the deletion has to survive a round trip that
 * ends with the session it was made from no longer being valid.
 */

test("an account's data can be downloaded as a file", async ({ page }) => {
  await signUp(page, "exporter");

  await page.getByRole("navigation").getByRole("link", { name: "Account" }).click();

  const saving = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download my data" }).click();
  const file = await saving;

  // Named by the server rather than by the path, so it lands in somebody's downloads
  // folder as something they can recognise a year later.
  expect(file.suggestedFilename()).toMatch(/^plantopia-export-.+\.zip$/);
  expect(await file.path()).toBeTruthy();
});

test("an account can be deleted, and only with both confirmations", async ({ page }) => {
  const address = await signUp(page, "leaver");

  await page.getByRole("navigation").getByRole("link", { name: "Account" }).click();
  await page.getByRole("button", { name: "Delete my account" }).click();

  // What it costs, before it happens.
  const warning = page.getByRole("alert");
  await expect(warning).toContainText(/photographs/i);
  await expect(warning).toContainText(/conversation/i);

  // The wrong password is refused, and the account survives it.
  await page.getByLabel("Your password", { exact: true }).fill("not-the-password");
  await page.getByLabel(/to confirm/i).fill("delete my account");
  await page.getByRole("button", { name: "Delete everything" }).click();
  await expect(page.getByText(/password is not correct/i)).toBeVisible();

  // So is the right password without the phrase.
  await page.getByLabel("Your password", { exact: true }).fill(PASSWORD);
  await page.getByLabel(/to confirm/i).fill("yes");
  await page.getByRole("button", { name: "Delete everything" }).click();
  await expect(page.getByText(/confirmation phrase does not match/i)).toBeVisible();

  // Both, and it goes.
  await page.getByLabel(/to confirm/i).fill("delete my account");
  await page.getByRole("button", { name: "Delete everything" }).click();

  // Signed out on the way past, rather than left holding a token for an account that no
  // longer exists.
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible({
    timeout: 30_000,
  });

  // And the credentials no longer work — refused the same way an unknown address is.
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
