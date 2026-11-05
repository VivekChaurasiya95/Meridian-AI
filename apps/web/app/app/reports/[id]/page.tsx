"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { ReportSection } from "@/components/investigations/ReportSection";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  MeridianApiError,
  formatBytes,
  formatTimestamp,
  getReport,
  issueReportDownload,
} from "@/lib/api";
import type { Report, ReportStatus } from "@/lib/types";

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

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [report, setReport] = React.useState<Report | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [downloading, setDownloading] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setReport(await getReport(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this report.");
    }
  }, [id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    if (report === null || (report.status !== "queued" && report.status !== "running")) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void load();
    }, 4000);
    return () => clearInterval(timer);
  }, [report, load]);

  async function onDownload() {
    if (report === null) return;
    setDownloading(true);
    setActionError(null);
    try {
      const { url } = await issueReportDownload(report.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setActionError(
        err instanceof MeridianApiError ? err.message : "Could not issue a download URL.",
      );
    } finally {
      setDownloading(false);
    }
  }

  if (error !== null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
        <Alert tone="danger" title="Not available">
          {error}
        </Alert>
        <Link href="/app/reports" className="text-[13px] font-semibold text-accent">
          Back to reports
        </Link>
      </div>
    );
  }

  if (report === null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-6 py-10" aria-label="Loading report">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
      <div>
        <Link
          href="/app/reports"
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-3 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to reports
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-display text-[28px] leading-tight font-semibold tracking-[-0.01em]">
            Report .{report.format}
          </h1>
          <Badge tone={STATUS_TONE[report.status]} dot={false}>
            {STATUS_LABEL[report.status]}
          </Badge>
        </div>
        <p className="mt-1 font-mono text-xs text-ink-3">
          generated {formatTimestamp(report.created_at)}
        </p>
      </div>

      {actionError !== null && (
        <Alert tone="danger" title="Action failed">
          {actionError}
        </Alert>
      )}

      {report.status === "blocked" && (
        <Alert tone="warning" title="Blocked">
          {report.error_message ??
            "An evidence artifact failed redaction review, so this report cannot be issued."}
        </Alert>
      )}

      {report.status === "failed" && (
        <Alert tone="danger" title="Generation failed">
          {report.error_message ?? "The report could not be generated."}
        </Alert>
      )}

      <ReportSection
        title="File"
        rows={[
          { label: "Report", value: report.id, mono: true },
          { label: "Format", value: report.format === "md" ? "Markdown (.md)" : "HTML (.html)" },
          { label: "Status", value: STATUS_LABEL[report.status] },
          { label: "SHA-256", value: report.digest_sha256 ?? "not issued", mono: true },
          {
            label: "Size",
            value: report.byte_size !== null ? formatBytes(report.byte_size) : "not issued",
          },
        ]}
      />

      <ReportSection
        title="Provenance"
        rows={[
          { label: "Investigation", value: report.investigation_id, mono: true },
          { label: "Project", value: report.project_id, mono: true },
          { label: "Patch", value: report.patch_id ?? "none at generation", mono: true },
          {
            label: "Verification run",
            value: report.verification_run_id ?? "none at generation",
            mono: true,
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={report.status !== "ready" || downloading}
          onClick={() => void onDownload()}
        >
          {downloading ? "Issuing…" : `Download .${report.format}`}
        </Button>
        <Link
          href={`/app/investigations/${report.investigation_id}`}
          className="inline-flex h-8 items-center rounded-[10px] border border-line px-3 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-2"
        >
          Open investigation
        </Link>
      </div>

      <p className="text-[13px] text-ink-3">
        Content is rendered only from recorded investigation state. Downloads are short-lived
        signed links issued for your session.
      </p>
    </div>
  );
}
