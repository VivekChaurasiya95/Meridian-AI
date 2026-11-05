"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  MeridianApiError,
  formatBytes,
  formatTimestamp,
  issueReportDownload,
  listWorkspaceReports,
  listWorkspaces,
} from "@/lib/api";
import type { Report, ReportStatus, Workspace } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

const STATUS_TONE: Record<ReportStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  queued: "neutral",
  running: "info",
  ready: "success",
  failed: "danger",
  blocked: "warning",
};

const STATUS_LABEL: Record<ReportStatus, string> = {
  queued: "Queued",
  running: "Generating",
  ready: "Ready",
  failed: "Failed",
  blocked: "Blocked",
};

export default function ReportsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [items, setItems] = React.useState<Report[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [downloading, setDownloading] = React.useState<string | null>(null);

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
          router.push("/login?next=%2Fapp%2Freports");
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
        setItems(await listWorkspaceReports(workspace));
        if (!silent) setError(null);
      } catch (err) {
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Freports");
          return;
        }
        if (!silent) setError(err instanceof Error ? err.message : "Could not load reports.");
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

  const live = items.some((report) => report.status === "queued" || report.status === "running");
  React.useEffect(() => {
    if (!live || !workspaceId) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void refresh(workspaceId, true);
    }, 5000);
    return () => clearInterval(timer);
  }, [live, workspaceId, refresh]);

  async function onDownload(report: Report) {
    setDownloading(report.id);
    setActionError(null);
    try {
      const { url } = await issueReportDownload(report.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setActionError(
        err instanceof MeridianApiError ? err.message : "Could not issue a download URL.",
      );
    } finally {
      setDownloading(null);
    }
  }

  if (loading && items.length === 0 && !error) {
    return (
      <div className="flex flex-col gap-6" aria-label="Loading reports">
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
            Reports
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">
            Investigation reports
          </h1>
          <p className="mt-1.5 text-[15px] text-ink-2">
            Deterministic documents rendered only from recorded state. Generate them from an
            investigation.
          </p>
        </div>
        {workspaces && workspaces.length > 0 && (
          <label className="flex items-center gap-2 text-[13px] text-ink-3">
            Workspace
            <select
              value={workspaceId ?? ""}
              onChange={(event) => {
                setWorkspaceId(event.target.value);
                router.replace(`/app/reports?workspace=${event.target.value}`);
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
          <Alert tone="danger" title="Reports unavailable">
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

      {actionError !== null && (
        <Alert tone="danger" title="Action failed">
          {actionError}
        </Alert>
      )}

      {workspaces !== null && workspaces.length === 0 && (
        <p className="text-[13px] text-ink-3">
          No workspaces yet — reports live inside a workspace.
        </p>
      )}

      {workspaces !== null && workspaces.length > 0 && items.length === 0 && error === null && (
        <p className="text-[13px] text-ink-3">
          No reports in this workspace yet — open an investigation and choose Generate report.
        </p>
      )}

      {items.length > 0 && (
        <ol className="flex flex-col gap-3">
          {items.map((report) => (
            <li key={report.id}>
              <Card className="flex flex-wrap items-center gap-3 px-5 py-4">
                <Badge tone={STATUS_TONE[report.status]} dot={false}>
                  {STATUS_LABEL[report.status]}
                </Badge>
                <Badge tone="neutral" dot={false}>
                  .{report.format}
                </Badge>
                <span className="font-mono text-xs text-ink-3">
                  {formatTimestamp(report.created_at)}
                  {report.byte_size !== null && ` · ${formatBytes(report.byte_size)}`}
                </span>
                {report.digest_sha256 !== null && (
                  <span
                    className="truncate font-mono text-[11px] text-ink-3"
                    title={`SHA-256: ${report.digest_sha256}`}
                  >
                    sha256:{report.digest_sha256.slice(0, 12)}…
                  </span>
                )}
                <span className="ml-auto flex gap-2">
                  <Link
                    href={`/app/reports/${report.id}`}
                    className="inline-flex h-8 items-center rounded-[10px] border border-line px-3 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-2"
                  >
                    Details
                  </Link>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={report.status !== "ready" || downloading === report.id}
                    onClick={() => void onDownload(report)}
                  >
                    {downloading === report.id ? "Issuing…" : `Download .${report.format}`}
                  </Button>
                </span>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
