import { expect, test } from "@playwright/test";

test("theme toggle switches between dark and light and persists", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).toHaveClass(/dark/);

  // The header toggle (the footer carries a second, identical one).
  await page.getByRole("banner").getByRole("button", { name: "Switch to light mode" }).click();
  await expect(html).not.toHaveClass(/dark/);
  await expect(
    page.getByRole("banner").getByRole("button", { name: "Switch to dark mode" }),
  ).toBeVisible();

  await page.reload();
  await expect(html).not.toHaveClass(/dark/);

  await page.getByRole("banner").getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(html).toHaveClass(/dark/);
});
