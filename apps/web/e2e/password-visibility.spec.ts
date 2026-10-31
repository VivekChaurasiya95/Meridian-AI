import { expect, test } from "@playwright/test";

/**
 * No API dependency: the toggle only flips the input type client-side, and
 * each field toggles independently.
 */
test("login password can be shown and hidden", async ({ page }) => {
  await page.goto("/login");
  const password = page.getByLabel("Password", { exact: true });
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show Password" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide Password" }).click();
  await expect(password).toHaveAttribute("type", "password");
});

test("signup passwords toggle independently", async ({ page }) => {
  await page.goto("/signup");
  const password = page.getByLabel("Password", { exact: true });
  const confirm = page.getByLabel("Confirm password", { exact: true });
  await page.getByRole("button", { name: "Show Confirm password" }).click();
  await expect(confirm).toHaveAttribute("type", "text");
  await expect(password).toHaveAttribute("type", "password");
});
