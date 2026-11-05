"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import {
  MeridianApiError,
  cancelInvestigation,
  formatBytes,
  formatTimestamp,
  getInvestigation,
  getInvestigationActivity,
  getInvestigationStages,
  getReadiness,
  issueEvidenceDownload,
  listHypotheses,
  listInvestigationEvidence,
  retryInvestigation,
} from "@/lib/api";
import type {
  ActivityEvent,
  EvidenceArtifact,
  Hypothesis,
  InvestigationDetail,
  InvestigationStage,
  InvestigationStatus,
  StageStatus,
} from "@/lib/types";
import { HypothesisCard } from "@/components/investigations/HypothesisCard";
import { PatchesSection } from "@/components/investigations/PatchesSection";
import { ReportsSection } from "@/components/investigations/ReportsSection";
import { TestsSection } from "@/components/investigations/TestsSection";
import { VerificationSection } from "@/components/investigations/VerificationSection";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { usePolling } from "@/lib/usePolling";

const STATUS_TONE: Record<InvestigationStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  failed: "danger",
  blocked: "warning",
  inconclusive: "warning",
  cancelled: "neutral",
};

const STAGE_TONE: Record<StageStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  pending: "neutral",
  running: "info",
  completed: "success",
  failed: "danger",
  blocked: "warning",
  skipped: "neutral",
  inconclusive: "warning",
  cancelled: "neutral",
};

const RETRYABLE = ["failed", "blocked", "inconclusive"];
const LIVE = ["queued", "running"];
const RETRY_STAGES = [
  "project_inspection",
  "reproduction",
  "evidence_analysis",
  "hypothesis_review",
  "regression_test_creation",
  "baseline_test_execution",
  "patch_proposal",
  "awaiting_user_approval",
  "patch_application",
  "post_patch_verification",
  "report_generation",
];

function prettyStage(key: string): string {
  return key.replace(/_/g, " ");
}

export default function InvestigationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const toast = useToast();
  const [detail, setDetail] = React.useState<InvestigationDetail | null>(null);
  const [stages, setStages] = React.useState<InvestigationStage[] | null>(null);
  const [activity, setActivity] = React.useState<ActivityEvent[] | null>(null);
  const [evidence, setEvidence] = React.useState<EvidenceArtifact[] | null>(null);
  const [hypotheses, setHypotheses] = React.useState<Hypothesis[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState(false);
  const [retryStage, setRetryStage] = React.useState("reproduction");
  const [retryReason, setRetryReason] = React.useState("");
  const [downloading, setDownloading] = React.useState<string | null>(null);
  const [modelState, setModelState] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      const [d, s, a, e, h] = await Promise.all([
        getInvestigation(id),
        getInvestigationStages(id),
        getInvestigationActivity(id),
        listInvestigationEvidence(id),
        listHypotheses(id),
      ]);
      setDetail(d);
      setStages(s);
      setActivity(a);
      setEvidence(e);
      setHypotheses(h);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this investigation.");
      return false;
    }
  }, [id]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    let live = true;
    getReadiness()
      .then((health) => {
        if (live) setModelState(health.checks.model ?? null);
      })
      .catch(() => {
        if (live) setModelState(null);
      });
    return () => {
      live = false;
    };
  }, []);

  const live = detail !== null && LIVE.includes(detail.status);
  usePolling(live, load, { baseMs: 4000 });

  async function onCancel() {
    setWorking(true);
    setActionError(null);
    try {
      const updated = await cancelInvestigation(id);
      setDetail((prev) => (prev === null ? prev : { ...prev, ...updated }));
      toast.success("Cancellation requested.");
      void load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel.");
    } finally {
      setWorking(false);
    }
  }

  async function onRetry(event: React.FormEvent) {
    event.preventDefault();
    setWorking(true);
    setActionError(null);
    try {
      const updated = await retryInvestigation(id, { from_stage: retryStage, reason: retryReason });
      setDetail((prev) => (prev === null ? prev : { ...prev, ...updated }));
      toast.success("Retry queued.");
      setRetryReason("");
      void load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not retry.");
    } finally {
      setWorking(false);
    }
  }

  async function onDownload(evidenceId: string) {
    setDownloading(evidenceId);
    setActionError(null);
    try {
      const { url } = await issueEvidenceDownload(evidenceId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setActionError(
        err instanceof MeridianApiError ? err.message : "Could not issue a download URL.",
      );
    } finally {
      setDownloading(null);
    }
  }

  if (error !== null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
        <Alert tone="danger" title="Not available">
          {error}
        </Alert>
        <Link href="/app/projects" className="text-[13px] font-semibold text-accent">
          Back to projects
        </Link>
      </div>
    );
  }

  if (detail === null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-6 py-10" aria-label="Loading investigation">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const terminal = !LIVE.includes(detail.status);
  const retryable = RETRYABLE.includes(detail.status);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
      <div>
        <Link
          href={`/app/projects/${detail.project_id}?tab=investigations`}
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-3 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to project
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-display text-[28px] leading-tight font-semibold tracking-[-0.01em]">
            {detail.title}
          </h1>
          <Badge tone={STATUS_TONE[detail.status]} dot={false}>
            {detail.status.replace("_", " ")}
          </Badge>
          <Badge tone="neutral" dot={false}>
            {detail.severity}
          </Badge>
          {modelState === "ok" && (
            <Badge tone="success" dot={false}>
              Model configured
            </Badge>
          )}
          {modelState === "not_configured" && (
            <span title="Reasoning stages wait until an operator configures a model provider.">
              <Badge tone="neutral" dot={false}>
                Model not configured
              </Badge>
            </span>
          )}
        </div>
        <p className="mt-1 font-mono text-xs text-ink-3">
          opened {formatTimestamp(detail.created_at)}
          {detail.current_stage !== null && ` · ${prettyStage(detail.current_stage)}`}
        </p>
      </div>

      {actionError !== null && (
        <Alert tone="danger" title="Action failed">
          {actionError}
        </Alert>
      )}

      {detail.result_summary !== null && (
        <Alert tone={detail.status === "completed" ? "success" : "warning"} title="Outcome">
          {detail.result_summary}
        </Alert>
      )}

      {!terminal && (
        <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-[13px] text-ink-2">
            {detail.cancel_requested
              ? "Cancellation requested — waiting for the worker to stop."
              : "This investigation is still running."}
          </p>
          <Button size="sm" variant="secondary" onClick={onCancel} disabled={working}>
            {working ? "Working…" : "Cancel investigation"}
          </Button>
        </Card>
      )}

      {retryable && (
        <Card className="flex flex-col gap-3 p-4">
          <h2 className="text-[15px] font-semibold">Retry from a stage</h2>
          <form onSubmit={onRetry} className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="retry-stage" className="text-[13px] font-semibold text-ink">
                Stage
              </label>
              <select
                id="retry-stage"
                value={retryStage}
                onChange={(event) => setRetryStage(event.target.value)}
                className="h-10 w-full rounded-[10px] border border-line bg-surface-1 px-3.5 text-[14px] text-ink outline-none focus:border-accent"
              >
                {RETRY_STAGES.map((stage) => (
                  <option key={stage} value={stage}>
                    {prettyStage(stage)}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="Reason"
              value={retryReason}
              onChange={(event) => setRetryReason(event.target.value)}
              placeholder="What changed since the last attempt?"
              maxLength={500}
            />
            <div>
              <Button type="submit" size="sm" disabled={working || retryReason.trim() === ""}>
                {working ? "Retrying…" : "Retry"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <section aria-label="Stages">
        <h2 className="mb-2 text-[15px] font-semibold">Stages</h2>
        {stages === null ? (
          <Skeleton className="h-24" />
        ) : stages.length === 0 ? (
          <p className="text-[13px] text-ink-3">No stages have run yet.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {stages.map((stage) => (
              <li key={stage.id}>
                <Card className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STAGE_TONE[stage.status]} dot={false}>
                      {stage.status}
                    </Badge>
                    <span className="text-[14px] font-semibold">{prettyStage(stage.stage_key)}</span>
                    {stage.attempt_number > 1 && (
                      <span className="font-mono text-xs text-ink-3">
                        attempt {stage.attempt_number}
                      </span>
                    )}
                    <span className="ml-auto font-mono text-xs text-ink-3">
                      {stage.finished_at !== null
                        ? formatTimestamp(stage.finished_at)
                        : stage.started_at !== null
                          ? `started ${formatTimestamp(stage.started_at)}`
                          : "pending"}
                    </span>
                  </div>
                  {stage.error_message !== null && (
                    <p className="mt-1.5 truncate text-[13px] text-danger" title={stage.error_message}>
                      {stage.error_code}: {stage.error_message}
                    </p>
                  )}
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Evidence">
        <h2 className="mb-2 text-[15px] font-semibold">
          Evidence {evidence !== null && evidence.length > 0 && `(${evidence.length})`}
        </h2>
        {evidence === null ? (
          <Skeleton className="h-24" />
        ) : evidence.length === 0 ? (
          <p className="text-[13px] text-ink-3">No evidence captured yet.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {evidence.map((item) => (
              <li key={item.id}>
                <Card className="flex flex-wrap items-center gap-3 p-4">
                  <Badge tone="neutral" dot={false}>
                    {item.kind.replace("_", " ")}
                  </Badge>
                  <span className="font-mono text-xs text-ink-3">
                    {item.mime_type} · {formatBytes(item.byte_size)}
                  </span>
                  <Badge
                    tone={item.redaction_status === "failed" ? "danger" : "success"}
                    dot={false}
                  >
                    {item.redaction_status.replace("_", " ")}
                  </Badge>
                  <span className="ml-auto">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={item.redaction_status === "failed" || downloading === item.id}
                      onClick={() => void onDownload(item.id)}
                    >
                      {downloading === item.id ? "Issuing…" : "Download"}
                    </Button>
                  </span>
                </Card>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Hypotheses">
        <h2 className="mb-2 text-[15px] font-semibold">
          Hypotheses {hypotheses !== null && hypotheses.length > 0 && `(${hypotheses.length})`}
        </h2>
        {hypotheses === null ? (
          <Skeleton className="h-24" />
        ) : hypotheses.length === 0 ? (
          <p className="text-[13px] text-ink-3">
            No hypotheses yet — they appear once the review stage runs.
          </p>
        ) : (
          <ol className="flex flex-col gap-2">
            {hypotheses.map((hypothesis) => (
              <li key={hypothesis.id}>
                <HypothesisCard hypothesis={hypothesis} onReviewed={() => void load()} />
              </li>
            ))}
          </ol>
        )}
      </section>

      <TestsSection investigationId={id} />

      <VerificationSection investigationId={id} />

      <PatchesSection investigationId={id} onChanged={() => void load()} />

      <ReportsSection investigationId={id} />

      <section aria-label="Activity">
        <h2 className="mb-2 text-[15px] font-semibold">Activity</h2>
        {activity === null ? (
          <Skeleton className="h-24" />
        ) : activity.length === 0 ? (
          <p className="text-[13px] text-ink-3">No activity yet.</p>
        ) : (
          <ol className="flex flex-col gap-0">
            {activity.map((event) => (
              <li key={event.id} className="flex gap-3 border-b border-line/60 py-2.5 last:border-0">
                <span className="w-36 shrink-0 pt-0.5 font-mono text-[11px] text-ink-3">
                  {formatTimestamp(event.created_at)}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] text-ink">{event.message}</p>
                  <p className="font-mono text-[11px] text-ink-3">{event.event_type}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
