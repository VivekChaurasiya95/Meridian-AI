import { expect, test } from "@playwright/test";
import { DEFAULT_API_BASE, resolveApiBase } from "../lib/api";

test("defaults to the documented local API port when NEXT_PUBLIC_API_URL is unset", () => {
  // Must match README / .env.example / docker-compose (host): the API serves 8010.
  expect(DEFAULT_API_BASE).toBe("http://localhost:8010");
});

/** Pure client tests: no browser, no server — they run in the e2e gate. */
test("keeps the configured API base for matching or foreign hosts", () => {
  expect(resolveApiBase("http://localhost:8010", "localhost")).toBe("http://localhost:8010");
  expect(resolveApiBase("http://localhost:8010", null)).toBe("http://localhost:8010");
  expect(resolveApiBase("http://localhost:8010", "192.168.1.10")).toBe("http://localhost:8010");
  expect(resolveApiBase("https://api.example.com", "localhost")).toBe("https://api.example.com");
  expect(resolveApiBase("not-a-url", "localhost")).toBe("not-a-url");
});

test("swaps loopback spellings so the cookie stays same-site", () => {
  expect(resolveApiBase("http://localhost:8010", "127.0.0.1")).toBe("http://127.0.0.1:8010");
  expect(resolveApiBase("http://127.0.0.1:8010", "localhost")).toBe("http://localhost:8010");
});
