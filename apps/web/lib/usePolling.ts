import * as React from "react";

interface PollingOptions {
  /** Base delay between ticks in ms. Defaults to 5000. */
  baseMs?: number;
  /** Backoff ceiling in ms. Defaults to 60000. */
  maxMs?: number;
}

/**
 * Visibility-aware polling with exponential backoff on failure.
 *
 * The tick runs on a timeout chain (not a fixed interval) so a failing
 * endpoint backs off instead of hammering it: each consecutive failure
 * doubles the delay up to `maxMs`, and any success resets it. Ticks are
 * skipped while the tab is hidden; returning to the tab triggers an
 * immediate refresh. A tick reports failure by throwing or returning
 * exactly `false`.
 */
export function usePolling(
  enabled: boolean,
  tick: () => Promise<unknown> | unknown,
  options?: PollingOptions,
): void {
  const baseMs = options?.baseMs ?? 5000;
  const maxMs = options?.maxMs ?? 60000;
  const tickRef = React.useRef(tick);
  tickRef.current = tick;

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let failures = 0;

    async function run() {
      if (cancelled) return;
      if (document.visibilityState === "hidden") {
        schedule(baseMs);
        return;
      }
      let failed = false;
      try {
        failed = (await tickRef.current()) === false;
      } catch {
        failed = true;
      }
      if (cancelled) return;
      failures = failed ? failures + 1 : 0;
      const delay = failed ? Math.min(baseMs * 2 ** failures, maxMs) : baseMs;
      schedule(delay);
    }

    function schedule(delay: number) {
      if (cancelled) return;
      timer = setTimeout(() => void run(), delay);
    }

    function onVisible() {
      if (cancelled || document.visibilityState === "hidden") return;
      if (timer !== null) clearTimeout(timer);
      void run();
    }

    // The first tick waits a full delay: callers already load once
    // themselves, and the hook only keeps live data fresh.
    schedule(baseMs);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, baseMs, maxMs]);
}
