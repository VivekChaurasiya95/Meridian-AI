"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { usePolling } from "@/lib/usePolling";
import {
  VERDICT_LABEL,
  VerificationSummary,
  formatDuration,
} from "@/components/investigations/VerificationSummary";
import {
  MeridianApiError,
  createVerificationRun,
  getVerificationComparison,
  issueEvidenceDownload,
  listRegressionTests,
  listVerificationRuns,
} from "@/lib/api";
import type {
  RegressionTest,
  VerificationComparison,
  VerificationRun,
} from "@/lib/types";

const RUNNABLE_STATUSES = new Set(["created", "baseline_failed"]);

function isRunnable(test: RegressionTest): boolean {
  return (
    RUNNABLE_STATUSES.has(test.status) &&
    test.test_type === "e2e" &&
    test.created_artifact_id !== null
  );
}

/** Verification section: runs, baseline-vs-post comparison, and rerun (INV-09, M9).
 *
 * Runs render on an M8 backend; comparison and rerun are M9 controls and
 * stay hidden until their endpoint exists.
 */
export function VerificationSection({ investigationId }: { investigationId: string }) {
  const toast = useToast();
  const [runs, setRuns] = React.useState<VerificationRun[] | null>(null);
  const [comparison, setComparison] = React.useState<VerificationComparison | null>(null);
  const [tests, setTests] = React.useState<RegressionTest[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [creating, setCreating] = React.useState(false);
  const [downloading, setDownloading] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      const [r, t] = await Promise.all([
        listVerificationRuns(investigationId),
        listRegressionTests(investigationId),
      ]);
      // The comparison endpoint is M9: a 404 means an older backend, so
      // degrade to runs-only instead of failing the whole section.
      let c: VerificationComparison | null = null;
      try {
        c = await getVerificationComparison(investigationId);
      } catch (err) {
        if (!(err instanceof MeridianApiError) || err.status !== 404) throw err;
      }
      setRuns(r);
      setComparison(c);
      setTests(t);
      setError(null);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load verification.");
      return false;
    }
  }, [investigationId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const live = runs?.some((run) => run.status === "queued" || run.status === "running") ?? false;
  usePolling(live, load, { baseMs: 5000 });

  function openForm() {
    setActionError(null);
    setSelected((tests ?? []).filter(isRunnable).map((test) => test.id));
    setFormOpen(true);
  }

  function toggle(id: string) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((key) => key !== id) : [...prev, id]));
  }

  async function onRerun(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setActionError(null);
    try {
      await createVerificationRun(investigationId, { selected_check_keys: selected });
      setFormOpen(false);
      toast.success("Verification run queued.");
      void load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not queue a new run.");
    } finally {
      setCreating(false);
    }
  }

  async function onViewLogs(artifactId: string) {
    setDownloading(true);
    setActionError(null);
    try {
      const { url } = await issueEvidenceDownload(artifactId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setActionError(
        err instanceof MeridianApiError ? err.message : "Could not issue a download URL.",
      );
    } finally {
      setDownloading(false);
    }
  }

  if (error !== null && runs === null) {
    return (
      <section aria-label="Verification">
        <h2 className="mb-2 text-[15px] font-semibold">Verification</h2>
        <Alert tone="danger" title="Verification unavailable">
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

  if (runs === null || tests === null) {
    return (
      <section aria-label="Verification">
        <h2 className="mb-2 text-[15px] font-semibold">Verification</h2>
        <Skeleton className="h-32" />
      </section>
    );
  }

  const runnable = tests.filter(isRunnable);
  const [latest, ...older] = runs;
  const m9 = comparison !== null;

  return (
    <section aria-label="Verification">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold">
          Verification {runs.length > 0 && `(${runs.length})`}
        </h2>
        {m9 && (
          <span className="ml-auto">
            <Button size="sm" variant="secondary" onClick={openForm} disabled={runnable.length === 0}>
              Rerun verification
            </Button>
          </span>
        )}
      </div>

      {actionError !== null && (
        <div className="mb-2">
          <Alert tone="danger" title="Action failed">
            {actionError}
          </Alert>
        </div>
      )}

      {formOpen && (
        <Card className="mb-2 flex flex-col gap-3 p-4">
          <h3 className="text-[14px] font-semibold">Queue a new run</h3>
          <p className="text-[13px] text-ink-2">
            A rerun queues a new run without changing history. Unselected tests keep their current
            status.
          </p>
          <form onSubmit={onRerun} className="flex flex-col gap-2">
            <fieldset className="flex flex-col gap-1.5">
              <legend className="sr-only">Checks to run</legend>
              {runnable.map((test) => (
                <label
                  key={test.id}
                  className="flex cursor-pointer items-center gap-2.5 rounded-md border border-line/70 bg-inset px-3 py-2 text-[13px]"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(test.id)}
                    onChange={() => toggle(test.id)}
                    className="size-4 accent-[var(--color-accent)]"
                  />
                  <span className="min-w-0 flex-1 truncate font-medium">{test.title}</span>
                  <span className="font-mono text-[11px] text-ink-3">{test.status}</span>
                </label>
              ))}
            </fieldset>
            <p className="font-mono text-[11px] text-ink-3">
              {selected.length} of {runnable.length} runnable checks selected
              {tests.length > runnable.length &&
                ` · ${tests.length - runnable.length} test(s) not runnable`}
            </p>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={creating || selected.length === 0}>
                {creating ? "Queueing…" : "Queue run"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={creating}
                onClick={() => setFormOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {runs.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          No verification runs yet — checks appear once the test stages run
          {m9 && runnable.length > 0 && ", or queue a rerun above"}.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {latest !== undefined && (
            <VerificationSummary run={latest} onViewLogs={onViewLogs} logsBusy={downloading} />
          )}
          {older.map((run) => (
            <details key={run.id} className="group rounded-xl border border-line bg-surface-1">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-4 py-3 text-[13px] [&::-webkit-details-marker]:hidden">
                <Badge tone="neutral" dot={false}>
                  {run.phase.replace("_", " ")}
                </Badge>
                <span className="font-semibold">{VERDICT_LABEL[run.status]}</span>
                <span className="font-mono text-[11px] text-ink-3">
                  {(run.checks ?? []).length} check(s)
                </span>
                <span className="ml-auto font-mono text-[11px] text-ink-3">
                  {run.finished_at ?? run.created_at}
                </span>
              </summary>
              <div className="px-2 pb-2">
                <VerificationSummary run={run} onViewLogs={onViewLogs} logsBusy={downloading} />
              </div>
            </details>
          ))}
        </div>
      )}

      {comparison !== null && comparison.tests.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-[14px] font-semibold">Baseline vs post-patch</h3>
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-[12px] text-ink-2">
                  <th scope="col" className="px-3.5 py-2.5 font-semibold">
                    Test
                  </th>
                  <th scope="col" className="px-3.5 py-2.5 font-semibold">
                    Baseline
                  </th>
                  <th scope="col" className="px-3.5 py-2.5 font-semibold">
                    Post-patch
                  </th>
                </tr>
              </thead>
              <tbody>
                {comparison.tests.map((row) => (
                  <tr key={row.test_id} className="border-b border-line/60 last:border-0">
                    <th scope="row" className="px-3.5 py-2.5 font-medium text-ink">
                      {row.title}
                    </th>
                    <td className="px-3.5 py-2.5">
                      {row.baseline === null ? (
                        <span className="text-ink-3">—</span>
                      ) : (
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          <Badge tone="neutral" dot={false}>
                            {VERDICT_LABEL[row.baseline.check_status]}
                          </Badge>
                          <span className="font-mono text-[11px] text-ink-3">
                            {formatDuration(row.baseline.duration_ms)}
                          </span>
                        </span>
                      )}
                    </td>
                    <td className="px-3.5 py-2.5">
                      {row.post_patch === null ? (
                        <span className="text-ink-3">—</span>
                      ) : (
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          <Badge tone="neutral" dot={false}>
                            {VERDICT_LABEL[row.post_patch.check_status]}
                          </Badge>
                          <span className="font-mono text-[11px] text-ink-3">
                            {formatDuration(row.post_patch.duration_ms)}
                          </span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="mt-3 text-[12px] leading-5 text-ink-3">
        Verification reflects the checks executed in this environment. It does not guarantee the
        absence of all possible defects.
      </p>
    </section>
  );
}
