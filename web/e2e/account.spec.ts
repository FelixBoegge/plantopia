import { expect, test } from "@playwright/test";

import { PASSWORD, linkSentTo, pathOf, someone } from "./people";

/**
 * Getting an account, from nothing to signed in.
 *
 * The flow crosses four boundaries a component test mocks away: a form posting multipart to
 * a real API, an email being sent, a link in that email resolving to a route that exists,
 * and a token being spent exactly once. Every one of those has been wrong here at least
 * once, and none of the failures were visible to a green unit suite.
 */

test("registers, verifies and signs in", async ({ page }) => {
  const address = someone("new");

  await page.goto("/register");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByText(/check your (email|inbox)/i)).toBeVisible();

  // The link a person was actually sent, followed as sent. A test that minted its own token
  // would pass while every real link pointed somewhere that does not exist — which is
  // exactly what shipped once, at a retired UI's port.
  const link = await linkSentTo(address, page);
  expect(link).toContain("/verify-email?token=");

  await page.goto(pathOf(link));
  await expect(page.getByText("Your address is confirmed")).toBeVisible();

  await page.getByRole("link", { name: /sign in/i }).click();
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Your plants" })).toBeVisible();
});

test("refuses a link that has already been used", async ({ page }) => {
  // Not paranoia about the server: the screen sends the request itself, on arrival, and a
  // remount that sent it twice would burn a real person's only link. StrictMode found that
  // once already.
  const address = someone("twice");

  await page.goto("/register");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();

  const link = pathOf(await linkSentTo(address, page));
  await page.goto(link);
  await expect(page.getByText("Your address is confirmed")).toBeVisible();

  await page.goto(link);
  await expect(page.getByText("That link cannot be used")).toBeVisible();
});

test("keeps somebody signed in across a reload", async ({ page }) => {
  // The access token lives in a module closure and nowhere else, so a reload has nothing to
  // read: the session is rebuilt from the refresh cookie or it is gone. Which makes this
  // the one test that proves the cookie is actually being set and sent.
  const address = someone("reload");

  await page.goto("/register");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await page.goto(pathOf(await linkSentTo(address, page)));

  await page.goto("/login");
  await page.getByLabel("Email").fill(address);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your plants" })).toBeVisible();

  await page.reload();

  await expect(page.getByRole("heading", { name: "Your plants" })).toBeVisible();
  await expect(page).toHaveURL(/\/$/);

  // Twice, deliberately, and this is the test that found the bug. `AuthProvider` used to
  // request `/auth/refresh` itself rather than going through the serialised `renew`, so
  // StrictMode's double effect fired two refreshes on every load. The second presented the
  // token the first had already rotated, the server correctly read that as a replayed
  // credential and revoked the whole family — so the *next* reload signed the person out.
  //
  // It cannot be caught in jsdom. The component suite mounts in StrictMode too, but a mocked
  // refresh endpoint has no rotation to replay, so both calls succeed and nothing is wrong.
  // What makes this visible is a real server that rotates and a real cookie jar.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your plants" })).toBeVisible();
});
