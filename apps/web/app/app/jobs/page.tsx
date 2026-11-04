"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, FlaskConical, Play, XCircle } from "lucide-react";
import {
  MeridianApiError,
  cancelJob,
  formatTimestamp,
  getJobStages,
  listJobs,
  listWorkspaces,
  submitJob,
} from "@/lib/api";
import type { Job, JobStage, JobStatus, Workspace } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

const POLL_MS = 5000;

const STATUS_FILTERS: { key: JobStatus | null; label: string }[] = [
  { key: null, label: "All" },
  { key: "queued", label: "Queued" },
  { key: "running", label: "Running" },
  { key: "retry_wait", label: "Retrying" },
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
  { key: "cancelled", label: "Cancelled" },
];

function statusTone(status: JobStatus): "accent" | "neutral" | "success" | "warning" | "danger" | "info" {
  if (status === "queued") return "neutral";
  if (status === "running") return "info";
  if (status === "retry_wait") return "warning";
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  return "neutral";
}

function statusLabel(status: JobStatus): string {
  if (status === "retry_wait") return "Retrying";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function JobRow({ job, onChanged }: { job: Job; onChanged: (job: Job) => void }) {
  const [open, setOpen] = React.useState(false);
  const [stages, setStages] = React.useState<JobStage[] | null>(null);
  const [stagesError, setStagesError] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const live = job.status === "queued" || job.status === "running" || job.status === "retry_wait";

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && stages === null) {
      try {
        setStages(await getJobStages(job.id));
      } catch (err) {
        setStagesError(err instanceof Error ? err.message : "Could not load stages.");
      }
    }
  }

  async function handleCancel() {
    setWorking(true);
    setActionError(null);
    try {
      onChanged(await cancelJob(job.id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel the job.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <li>
      <Card>
        <button
          type="button"
          onClick={() => void toggle()}
          aria-expanded={open}
          className="flex w-full cursor-pointer items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-surface-2/50 sm:px-6"
        >
          <span
            aria-hidden="true"
            className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-sage-subtle text-sage"
          >
            <FlaskConical className="size-4" />
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[13px] font-semibold text-ink">{job.job_type}</span>
              <Badge tone={statusTone(job.status)} pulse={live} dot={false}>
                {statusLabel(job.status)}
              </Badge>
            </span>
            <span className="truncate font-mono text-xs text-ink-3">
              {job.id.slice(0, 8)} · attempt {job.attempts}/{job.max_attempts}
              {job.worker_id ? ` · ${job.worker_id}` : ""} · {formatTimestamp(job.created_at)}
            </span>
            {job.error_message && (job.status === "failed" || job.status === "retry_wait") && (
              <span className="truncate text-[13px] text-danger">
                {job.error_code}: {job.error_message}
              </span>
            )}
          </span>
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "size-4 shrink-0 text-ink-3 transition-transform duration-200",
              open && "rotate-90",
            )}
          />
        </button>
        {open && (
          <div className="border-t border-line/70 px-5 py-4 sm:px-6">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] tracking-[0.12em] text-ink-3 uppercase">
                Stages
              </span>
              {live && (
                <span className="ml-auto">
                  <Button size="sm" variant="secondary" loading={working} onClick={() => void handleCancel()}>
                    <XCircle aria-hidden="true" className="size-3.5" /> Cancel job
                  </Button>
                </span>
              )}
            </div>
            {actionError && (
              <p className="mt-2 text-[13px] font-medium text-danger" role="alert">
                {actionError}
              </p>
            )}
            {stagesError && <p className="mt-2 text-[13px] text-danger">{stagesError}</p>}
            {stages === null && !stagesError && (
              <div className="mt-3 flex flex-col gap-2" aria-label="Loading stages">
                <Skeleton className="h-8" />
              </div>
            )}
            {stages !== null && stages.length === 0 && (
              <p className="mt-2 text-[13px] text-ink-3">
                No stages recorded yet — the worker writes them as it runs.
              </p>
            )}
            {stages !== null && stages.length > 0 && (
              <ol className="mt-3 flex flex-col">
                {stages.map((stage) => (
                  <li
                    key={stage.id}
                    className="flex items-center gap-3 border-t border-line/60 py-2 first:border-0 first:pt-0 last:pb-0"
                  >
                    <Badge
                      tone={
                        stage.status === "completed"
                          ? "success"
                          : stage.status === "failed"
                            ? "danger"
                            : stage.status === "running"
                              ? "info"
                              : "neutral"
                      }
                      dot={false}
                    >
                      {stage.status}
                    </Badge>
                    <span className="min-w-0 flex-1 truncate font-mono text-[13px]">
                      {stage.stage_key}
                      {stage.attempt > 1 && (
                        <span className="text-ink-3"> · attempt {stage.attempt}</span>
                      )}
                    </span>
                    {stage.error_message && (
                      <span className="max-w-xs truncate text-xs text-danger" title={stage.error_message}>
                        {stage.error_message}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </Card>
    </li>
  );
}

export default function JobsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [items, setItems] = React.useState<Job[]>([]);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState<JobStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

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
          router.push("/login?next=%2Fapp%2Fjobs");
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
    async (workspace: string, status: JobStatus | null, silent: boolean) => {
      try {
        const page = await listJobs(workspace, { limit: 25, status });
        setItems(page.items);
        setNextCursor(page.page.next_cursor);
        if (!silent) setError(null);
      } catch (err) {
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fjobs");
          return;
        }
        if (!silent) setError(err instanceof Error ? err.message : "Could not load jobs.");
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  React.useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    void refresh(workspaceId, statusFilter, false);
    const timer = setInterval(() => void refresh(workspaceId, statusFilter, true), POLL_MS);
    return () => clearInterval(timer);
  }, [workspaceId, statusFilter, refresh]);

  async function handleSubmitTest() {
    if (!workspaceId) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const job = await submitJob(workspaceId, {
        job_type: "lifecycle_test",
        payload: { note: "console smoke test" },
        idempotency_key: `console-${Date.now()}`,
      });
      setItems((current) => [job, ...current]);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Could not submit the job.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && items.length === 0 && !error) {
    return (
      <div className="flex flex-col gap-6" aria-label="Loading jobs">
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
            Jobs
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">
            Background jobs
          </h1>
          <p className="mt-1.5 text-[15px] text-ink-2">
            Durable work the cluster runs for this workspace. Statuses refresh every few
            seconds — no fake progress.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {workspaces && workspaces.length > 0 && (
            <label className="flex items-center gap-2 text-[13px] text-ink-3">
              Workspace
              <select
                value={workspaceId ?? ""}
                onChange={(event) => {
                  setWorkspaceId(event.target.value);
                  router.replace(`/app/jobs?workspace=${event.target.value}`);
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
          <Button loading={submitting} onClick={() => void handleSubmitTest()} disabled={!workspaceId}>
            <Play aria-hidden="true" className="size-4" /> Run test job
          </Button>
        </div>
      </div>

      {submitError && (
        <Alert tone="danger" title="Could not submit the job">
          {submitError}
        </Alert>
      )}
      {error && (
        <Alert tone="danger" title="Could not load jobs">
          {error}
        </Alert>
      )}

      {!workspaceId && !loading ? (
        <Alert tone="info" title="Create a workspace first">
          Jobs belong to a workspace.{" "}
          <Link href="/app" className="font-semibold underline">
            Back to overview
          </Link>
        </Alert>
      ) : (
        <>
          <div
            role="group"
            aria-label="Status filter"
            className="flex w-fit flex-wrap items-center gap-1 rounded-full border border-line bg-surface-1 p-1"
          >
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.label}
                type="button"
                onClick={() => setStatusFilter(filter.key)}
                aria-pressed={statusFilter === filter.key}
                className={cn(
                  "cursor-pointer rounded-full px-3 py-1.5 text-[13px] font-semibold transition-colors duration-200",
                  statusFilter === filter.key ? "bg-ink text-canvas" : "text-ink-3 hover:text-ink",
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {items.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-2">
                  <FlaskConical aria-hidden="true" className="size-5 text-sage" />
                </span>
                <div>
                  <p className="font-medium">No jobs yet</p>
                  <p className="mt-1 text-[13px] text-ink-2">
                    Run a lifecycle test job to watch the queue, lease, and stages work.
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <ul className="flex flex-col gap-3" aria-label="Jobs" aria-live="polite">
              {items.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  onChanged={(updated) =>
                    setItems((current) => current.map((j) => (j.id === updated.id ? updated : j)))
                  }
                />
              ))}
            </ul>
          )}
          {nextCursor && (
            <p className="font-mono text-xs text-ink-3">
              Older jobs are available through the API cursor.
            </p>
          )}
        </>
      )}
    </div>
  );
}
