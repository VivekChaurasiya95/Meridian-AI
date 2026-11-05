"use client";

import * as React from "react";
import { getLiveness } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { usePolling } from "@/lib/usePolling";

type Health = "checking" | "operational" | "unreachable";

/** Small API-liveness indicator for the topbar. Polls every 30 seconds. */
export function HealthBadge() {
  const [health, setHealth] = React.useState<Health>("checking");

  const probe = React.useCallback(async () => {
    try {
      const result = await getLiveness();
      setHealth(result.status === "ok" ? "operational" : "unreachable");
      return result.status === "ok";
    } catch {
      setHealth("unreachable");
      return false;
    }
  }, []);

  React.useEffect(() => {
    void probe();
  }, [probe]);

  usePolling(true, probe, { baseMs: 30_000, maxMs: 300_000 });

  if (health === "checking") return <Badge tone="neutral" pulse className="max-sm:hidden">API · Checking</Badge>;
  if (health === "operational") return <Badge tone="success" pulse className="max-sm:hidden">API · Operational</Badge>;
  return <Badge tone="danger" className="max-sm:hidden">API · Unreachable</Badge>;
}
