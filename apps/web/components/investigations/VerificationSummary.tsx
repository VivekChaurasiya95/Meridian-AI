"use client";

import * as React from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatTimestamp } from "@/lib/api";
import type {
  VerificationCheck,
  VerificationCheckStatus,
  VerificationPhase,
  VerificationRun,
  VerificationRunStatus,
} from "@/lib/types";

type Verdict = VerificationCheckStatus | VerificationRunStatus;

export const VERDICT_LABEL: Record<Verdict, string> = {
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
  skipped: "Skipped",
  timed_out: "Timed out",
  inconclusive: "Inconclusive",
  queued: "Queued",
  running: "Running",
  cancelled: "Cancelled",
};

const VERDICT_TONE: Record<Verdict, BadgeTone> = {
  passed: "success",
  failed: "danger",
  blocked: "warning",
  skipped: "neutral",
  timed_out: "warning",
  inconclusive: "neutral",
  queued: "neutral",
  running: "info",
  cancelled: "neutral",
};

export const PHASE_LABEL: Record<VerificationPhase, string> = {
  baseline: "Baseline",
  post_patch: "Post-patch",
  regression_test: "Regression test",
  diagnostic: "Diagnostic",
};

export function formatDuration(durationMs: number | null): string {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) return "—";
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(durationMs < 10000 ? 1 : 0)} s`;
}

export function VerificationCheckRow({
  check,
  onViewLogs,
  logsBusy,
}: {
  check: VerificationCheck;
  onViewLogs: (artifactId: string) => void;
  logsBusy: boolean;
}) {
  const logArtifact = check.stdout_artifact_id ?? check.stderr_artifact_id;
  return (
    <li>
      <Card tone="inset" className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
        <Badge tone={VERDICT_TONE[check.status]}>{VERDICT_LABEL[check.status]}</Badge>
        <span className="min-w-0 flex-1 basis-40 truncate text-[13px] font-semibold text-ink">
          {check.display_name}
        </span>
        <span className="font-mono text-[11px] text-ink-3">
          {formatDuration(check.duration_ms)}
          {check.exit_code !== null && ` · exit ${check.exit_code}`}
        </span>
        <Button
          size="sm"
          variant="secondary"
          disabled={logArtifact === null || logsBusy}
          onClick={() => logArtifact !== null && onViewLogs(logArtifact)}
        >
          {logsBusy ? "Opening…" : "View logs"}
        </Button>
      </Card>
    </li>
  );
}

function countBy(checks: VerificationCheck[]): Partial<Record<VerificationCheckStatus, number>> {
  const counts: Partial<Record<VerificationCheckStatus, number>> = {};
  for (const check of checks) counts[check.status] = (counts[check.status] ?? 0) + 1;
  return counts;
}

/** One verification run: aggregate status, counts, and per-check rows (INV-09). */
export function VerificationSummary({
  run,
  onViewLogs,
  logsBusy,
}: {
  run: VerificationRun;
  onViewLogs: (artifactId: string) => void;
  logsBusy: boolean;
}) {
  const checks = run.checks ?? [];
  const counts = countBy(checks);
  const planned = run.runtime_profile.planned_checks ?? [];
  const withheld = (counts.skipped ?? 0) + (counts.blocked ?? 0) > 0;
  const pending = run.status === "queued" || run.status === "running";

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={VERDICT_TONE[run.status]}>{VERDICT_LABEL[run.status]}</Badge>
        <Badge tone="neutral" dot={false}>
          {PHASE_LABEL[run.phase] ?? run.phase}
        </Badge>
        {run.patch_id !== null && (
          <span className="font-mono text-[11px] text-ink-3">patch {run.patch_id.slice(0, 8)}</span>
        )}
        <span className="ml-auto font-mono text-[11px] text-ink-3">
          {run.finished_at !== null
            ? formatTimestamp(run.finished_at)
            : run.started_at !== null
              ? `started ${formatTimestamp(run.started_at)}`
              : `queued ${formatTimestamp(run.created_at)}`}
        </span>
      </div>

      {run.summary !== null && <p className="text-[13px] text-ink-2">{run.summary}</p>}

      {checks.length > 0 && (
        <p className="font-mono text-[11px] text-ink-3" aria-label="Check counts">
          {(
            ["passed", "failed", "blocked", "skipped", "timed_out", "inconclusive"] as const
          )
            .filter((status) => (counts[status] ?? 0) > 0)
            .map((status) => `${counts[status]} ${VERDICT_LABEL[status].toLowerCase()}`)
            .join(" · ")}
        </p>
      )}

      {withheld && (
        <p className="text-[13px] text-ink-2">
          Required checks were skipped or blocked — this run does not establish a verified fix.
        </p>
      )}

      {pending && checks.length === 0 && planned.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[13px] text-ink-2">
            {run.status === "queued"
              ? "Queued — the worker picks this plan up on its next baseline or post-patch leg."
              : "Running — checks appear here as they execute."}
          </p>
          <ul className="flex flex-col gap-1" aria-label="Planned checks">
            {planned.map((item) => (
              <li
                key={item.check_key}
                className="truncate rounded-md border border-line/70 bg-inset px-3 py-1.5 text-[13px] text-ink-2"
              >
                {item.display_name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {pending && checks.length === 0 && planned.length === 0 && (
        <p className="text-[13px] text-ink-3">
          {run.status === "queued" ? "Queued — waiting for the worker." : "Running…"}
        </p>
      )}

      {!pending && checks.length === 0 && (
        <p className="text-[13px] text-ink-3">No checks were recorded for this run.</p>
      )}

      {checks.length > 0 && (
        <ol className="flex flex-col gap-1.5" aria-label="Checks">
          {checks.map((check) => (
            <VerificationCheckRow
              key={check.id}
              check={check}
              onViewLogs={onViewLogs}
              logsBusy={logsBusy}
            />
          ))}
        </ol>
      )}
    </Card>
  );
}
