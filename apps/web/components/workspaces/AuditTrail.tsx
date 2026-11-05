"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatTimestamp, listAuditEvents } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

/** Append-only workspace audit trail (owner/admin). Paged newest-first. */
export function AuditTrail({ workspaceId }: { workspaceId: string }) {
  const [events, setEvents] = React.useState<AuditEvent[] | null>(null);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      const page = await listAuditEvents(workspaceId, { limit: 25 });
      setEvents(page.items);
      setCursor(page.page.next_cursor);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the audit trail.");
    }
  }, [workspaceId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (cursor === null) return;
    setLoadingMore(true);
    try {
      const page = await listAuditEvents(workspaceId, { limit: 25, cursor });
      setEvents((current) => [...(current ?? []), ...page.items]);
      setCursor(page.page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more events.");
    } finally {
      setLoadingMore(false);
    }
  }

  if (error !== null && events === null) {
    return (
      <section aria-label="Audit trail">
        <h2 className="text-[15px] font-semibold">Audit trail</h2>
        <div className="mt-2">
          <Alert tone="danger" title="Audit unavailable">
            {error}
          </Alert>
        </div>
        <div className="mt-2">
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  if (events === null) {
    return (
      <section aria-label="Audit trail">
        <h2 className="text-[15px] font-semibold">Audit trail</h2>
        <p className="mt-1 text-[13px] text-ink-3">Loading…</p>
      </section>
    );
  }

  return (
    <section aria-label="Audit trail">
      <h2 className="text-[15px] font-semibold">Audit trail</h2>
      <p className="mt-1 text-[13px] text-ink-2">
        Append-only record of sensitive actions — approvals, evidence downloads, membership
        changes.
      </p>
      {events.length === 0 ? (
        <p className="mt-2 text-[13px] text-ink-3">No audited actions yet.</p>
      ) : (
        <ol className="mt-2 flex flex-col gap-1.5">
          {events.map((event) => (
            <li
              key={event.id}
              className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 rounded-[10px] border border-line bg-surface-1 px-3 py-2"
            >
              <Badge tone="neutral" dot={false}>
                {event.action}
              </Badge>
              <span className="font-mono text-[11px] text-ink-3">
                {event.actor_type}
                {event.resource_type !== null && ` · ${event.resource_type}`}
                {event.resource_id !== null && ` ${event.resource_id.slice(0, 8)}`}
              </span>
              <span className="ml-auto font-mono text-[11px] text-ink-3">
                {formatTimestamp(event.created_at)}
              </span>
            </li>
          ))}
        </ol>
      )}
      {cursor !== null && (
        <div className="mt-2">
          <Button size="sm" variant="secondary" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}
    </section>
  );
}
