import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  // Local Windows runs crash parallel Chromium workers (0xC0000409);
  // CI keeps the default parallelism.
  workers: process.env.CI ? undefined : 1,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3010",
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "npm run dev",
        url: "http://localhost:3010",
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
