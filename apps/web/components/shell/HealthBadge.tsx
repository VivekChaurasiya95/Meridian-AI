"use client";

import * as React from "react";
import { getLiveness } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";

type Health = "checking" | "operational" | "unreachable";

/** Small API-liveness indicator for the topbar. Polls every 30 seconds. */
export function HealthBadge() {
  const [health, setHealth] = React.useState<Health>("checking");

  React.useEffect(() => {
    let cancelled = false;
    async function probe() {
      try {
        const result = await getLiveness();
        if (!cancelled) setHealth(result.status === "ok" ? "operational" : "unreachable");
      } catch {
        if (!cancelled) setHealth("unreachable");
      }
    }
    void probe();
    const timer = setInterval(() => void probe(), 30_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (health === "checking") return <Badge tone="neutral" pulse className="max-sm:hidden">API · Checking</Badge>;
  if (health === "operational") return <Badge tone="success" pulse className="max-sm:hidden">API · Operational</Badge>;
  return <Badge tone="danger" className="max-sm:hidden">API · Unreachable</Badge>;
}
