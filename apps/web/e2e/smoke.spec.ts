import { expect, test } from "@playwright/test";

/**
 * M1 smoke: the landing page renders honestly with no API dependency, and the
 * app shell renders its chrome. App-data flows get full e2e coverage at M2+.
 */
test("landing presents the product without fake claims", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "One pipeline, from report to verified fix." }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /open the workspace/i }).first()).toBeVisible();
  await expect(page.getByText("Concept preview", { exact: false })).toBeVisible();
  // No fabricated social proof anywhere on the page.
  await expect(page.getByText(/trusted by|testimonial|customers/i)).toHaveCount(0);
});

test("app shell redirects anonymous visitors to login", async ({ page }) => {
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp/);
  await expect(page.getByRole("heading", { name: "Sign in to Meridian" })).toBeVisible();
});

test("auth pages render honest forms with no API dependency", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await page.goto("/signup");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await expect(page.getByLabel("Confirm password", { exact: true })).toBeVisible();
});
