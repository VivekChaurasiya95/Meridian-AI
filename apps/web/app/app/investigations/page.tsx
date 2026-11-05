"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  MeridianApiError,
  formatTimestamp,
  listWorkspaceInvestigations,
  listWorkspaces,
} from "@/lib/api";
import type {
  Investigation,
  InvestigationSeverity,
  InvestigationStatus,
  Workspace,
} from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { usePolling } from "@/lib/usePolling";

const STATUS_TONE: Record<
  InvestigationStatus,
  "success" | "info" | "warning" | "danger" | "neutral"
> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  failed: "danger",
  blocked: "warning",
  inconclusive: "warning",
  cancelled: "neutral",
};

const STATUS_LABEL: Record<InvestigationStatus, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_approval: "Awaiting approval",
  completed: "Completed",
  failed: "Failed",
  blocked: "Blocked",
  inconclusive: "Inconclusive",
  cancelled: "Cancelled",
};

const SEVERITY_LABEL: Record<InvestigationSeverity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
  unspecified: "Unspecified",
};

export default function InvestigationsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [items, setItems] = React.useState<Investigation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function boot() {
      try {
        const { items: list } = await listWorkspaces(100);
        if (cancelled) return;
        setWorkspaces(list);
        if (workspaceParam) setWorkspaceId(workspaceParam);
        else if (list.length > 0) setWorkspaceId(list[0].id);
        else setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Finvestigations");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load workspaces.");
        setLoading(false);
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [router, workspaceParam]);

  const refresh = React.useCallback(
    async (workspace: string, silent: boolean) => {
      try {
        const { items: list } = await listWorkspaceInvestigations(workspace);
        if (!silent) setError(null);
        setItems(list);
        return true;
      } catch (err) {
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Finvestigations");
          return false;
        }
        if (!silent)
          setError(err instanceof Error ? err.message : "Could not load investigations.");
        return false;
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  React.useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    void refresh(workspaceId, false);
  }, [workspaceId, refresh]);

  const live = items.some(
    (investigation) =>
      investigation.status === "queued" || investigation.status === "running",
  );
  const poll = React.useCallback(
    () => (workspaceId ? refresh(workspaceId, true) : undefined),
    [workspaceId, refresh],
  );
  usePolling(live && workspaceId !== null, poll, { baseMs: 5000 });

  if (loading && items.length === 0 && !error) {
    return (
      <div className="flex flex-col gap-6" aria-label="Loading investigations">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-sage uppercase">
            Investigations
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">
            Debugging sessions
          </h1>
          <p className="mt-1.5 text-[15px] text-ink-2">
            Every investigation across this workspace, newest first. Open one to follow its
            stages, evidence, and patches.
          </p>
        </div>
        {workspaces && workspaces.length > 0 && (
          <label className="flex items-center gap-2 text-[13px] text-ink-3">
            Workspace
            <select
              value={workspaceId ?? ""}
              onChange={(event) => {
                setWorkspaceId(event.target.value);
                router.replace(`/app/investigations?workspace=${event.target.value}`);
              }}
              className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
            >
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error !== null && (
        <div className="flex flex-col gap-2">
          <Alert tone="danger" title="Investigations unavailable">
            {error}
          </Alert>
          <div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => workspaceId && void refresh(workspaceId, false)}
            >
              Retry
            </Button>
          </div>
        </div>
      )}

      {workspaces !== null && workspaces.length === 0 && (
        <p className="text-[13px] text-ink-3">
          No workspaces yet — investigations live inside a workspace.
        </p>
      )}

      {workspaces !== null && workspaces.length > 0 && items.length === 0 && error === null && (
        <p className="text-[13px] text-ink-3">
          No investigations in this workspace yet — open a project and describe a bug.
        </p>
      )}

      {items.length > 0 && (
        <ol className="flex flex-col gap-3">
          {items.map((investigation) => (
            <li key={investigation.id}>
              <Card className="flex flex-wrap items-center gap-3 px-5 py-4">
                <Badge tone={STATUS_TONE[investigation.status]} dot={false}>
                  {STATUS_LABEL[investigation.status]}
                </Badge>
                <Badge tone="neutral" dot={false}>
                  {SEVERITY_LABEL[investigation.severity]}
                </Badge>
                <Link
                  href={`/app/investigations/${investigation.id}`}
                  className="min-w-0 flex-1 truncate text-[15px] font-semibold text-ink hover:underline"
                >
                  {investigation.title}
                </Link>
                <span className="font-mono text-xs text-ink-3">
                  {formatTimestamp(investigation.created_at)}
                </span>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
