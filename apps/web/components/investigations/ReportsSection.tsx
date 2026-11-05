"use client";

import * as React from "react";
import Link from "next/link";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  MeridianApiError,
  createReport,
  formatBytes,
  formatTimestamp,
  issueReportDownload,
  listReports,
} from "@/lib/api";
import type { Report, ReportFormat, ReportStatus } from "@/lib/types";

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

/** Reports section: history, generate action, and downloads (M10). */
export function ReportsSection({ investigationId }: { investigationId: string }) {
  const [reports, setReports] = React.useState<Report[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [format, setFormat] = React.useState<ReportFormat>("md");
  const [creating, setCreating] = React.useState(false);
  const [downloading, setDownloading] = React.useState<string | null>(null);
  const [unsupported, setUnsupported] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setReports(await listReports(investigationId));
      setError(null);
    } catch (err) {
      // A missing endpoint means an older backend: hide the section
      // instead of alarming. Any other failure still surfaces.
      if (err instanceof MeridianApiError && err.status === 404) {
        setUnsupported(true);
        return;
      }
      setError(err instanceof Error ? err.message : "Could not load reports.");
    }
  }, [investigationId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const live = reports?.some((report) => report.status === "queued" || report.status === "running") ?? false;
  React.useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void load();
    }, 5000);
    return () => clearInterval(timer);
  }, [live, load]);

  if (unsupported) return null;

  async function onGenerate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setActionError(null);
    try {
      const created = await createReport(investigationId, { format });
      setReports((current) => (current === null ? [created] : [created, ...current]));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not generate a report.");
    } finally {
      setCreating(false);
    }
  }

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

  if (error !== null && reports === null) {
    return (
      <section aria-label="Reports">
        <h2 className="mb-2 text-[15px] font-semibold">Reports</h2>
        <Alert tone="danger" title="Reports unavailable">
          {error}
        </Alert>
        <div className="mt-2">
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  if (reports === null) {
    return (
      <section aria-label="Reports">
        <h2 className="mb-2 text-[15px] font-semibold">Reports</h2>
        <Skeleton className="h-24" />
      </section>
    );
  }

  return (
    <section aria-label="Reports">
      <h2 className="mb-2 text-[15px] font-semibold">
        Reports {reports.length > 0 && `(${reports.length})`}
      </h2>

      {actionError !== null && (
        <div className="mb-2">
          <Alert tone="danger" title="Action failed">
            {actionError}
          </Alert>
        </div>
      )}

      <Card className="mb-2 p-4">
        <form onSubmit={onGenerate} className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="report-format" className="text-[13px] font-semibold text-ink">
              Format
            </label>
            <select
              id="report-format"
              value={format}
              onChange={(event) => setFormat(event.target.value as ReportFormat)}
              className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[14px] text-ink outline-none focus:border-accent"
            >
              <option value="md">Markdown (.md)</option>
              <option value="html">HTML (.html)</option>
            </select>
          </div>
          <Button type="submit" size="sm" disabled={creating}>
            {creating ? "Generating…" : "Generate report"}
          </Button>
          <p className="w-full text-[13px] text-ink-3">
            Rendered only from recorded investigation state — every new report keeps history.
          </p>
        </form>
      </Card>

      {reports.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          No reports yet — generate one to capture the current state.
        </p>
      ) : (
        <ol className="flex flex-col gap-2">
          {reports.map((report) => (
            <li key={report.id}>
              <Card className="flex flex-wrap items-center gap-3 p-4">
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
                {report.error_message !== null && (
                  <span
                    className="w-full truncate text-[13px] text-danger"
                    title={report.error_message}
                  >
                    {report.error_code}: {report.error_message}
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
    </section>
  );
}
