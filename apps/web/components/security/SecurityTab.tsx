"use client";

import * as React from "react";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatTimestamp, listProjectAssessments } from "@/lib/api";
import type { SecurityAssessment, SecurityAssessmentStatus } from "@/lib/types";

const STATUS_TONE: Record<
  SecurityAssessmentStatus,
  "success" | "info" | "warning" | "danger" | "neutral"
> = {
  pending: "neutral",
  running: "info",
  completed: "success",
  review_required: "warning",
  partial: "warning",
  failed: "danger",
  cancelled: "neutral",
};

function AssessmentRow({ assessment }: { assessment: SecurityAssessment }) {
  const total = assessment.summary?.total ?? 0;
  return (
    <li>
      <Link
        href={`/app/security-assessments/${assessment.id}`}
        aria-label={`Open assessment from ${formatTimestamp(assessment.created_at)}`}
        className="block rounded-xl outline-none"
      >
        <Card className="flex flex-col gap-2 p-4 transition-colors hover:border-line-strong">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[assessment.status]} dot={false}>
              {assessment.status.replace(/_/g, " ")}
            </Badge>
            <span className="font-mono text-xs text-ink-3">
              {formatTimestamp(assessment.created_at)}
            </span>
            <span className="ml-auto font-mono text-[11px] text-ink-3">
              generation {assessment.generation} · {assessment.policy_version}
            </span>
          </div>
          <p className="text-[13px] text-ink-2">
            {total === 0
              ? "No issues detected by configured checks."
              : `${total} ${total === 1 ? "finding" : "findings"} detected by configured checks.`}
          </p>
          <p className="truncate font-mono text-[11px] text-ink-3">
            snapshot {assessment.snapshot_id.slice(0, 8)} · ruleset {assessment.ruleset_version}
          </p>
        </Card>
      </Link>
    </li>
  );
}

/**
 * Project assessments, newest first. Read-only: preflight checks run
 * automatically after snapshot storage; there is no scan trigger here.
 */
export function SecurityTab({ projectId }: { projectId: string }) {
  const [items, setItems] = React.useState<SecurityAssessment[] | null>(null);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      const page = await listProjectAssessments(projectId);
      setItems(page.items);
      setNextCursor(page.page.next_cursor);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load assessments.");
    }
  }, [projectId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (nextCursor === null) return;
    setLoadingMore(true);
    try {
      const page = await listProjectAssessments(projectId, { cursor: nextCursor });
      setItems((current) => [...(current ?? []), ...page.items]);
      setNextCursor(page.page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more assessments.");
    } finally {
      setLoadingMore(false);
    }
  }

  if (error !== null && items === null) {
    return (
      <div className="flex flex-col gap-2">
        <Alert tone="danger" title="Assessments unavailable">
          {error}
        </Alert>
        <div>
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (items === null) {
    return (
      <div className="flex flex-col gap-3" aria-label="Loading assessments">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-2">
            <ShieldCheck aria-hidden="true" className="size-5 text-sage" />
          </span>
          <div>
            <p className="font-medium">No assessments yet</p>
            <p className="mt-1 max-w-sm text-[13px] text-ink-2">
              Preflight checks run automatically once a snapshot is stored. Upload a snapshot,
              then check back here for its assessment.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error !== null && (
        <Alert tone="danger" title="Could not load more">
          {error}
        </Alert>
      )}
      <ol className="flex flex-col gap-3" aria-label="Assessments">
        {items.map((assessment) => (
          <AssessmentRow key={assessment.id} assessment={assessment} />
        ))}
      </ol>
      {nextCursor !== null && (
        <div>
          <Button variant="secondary" onClick={() => void loadMore()} loading={loadingMore}>
            Load more
          </Button>
        </div>
      )}
      <p className="text-[12px] leading-5 text-ink-3">
        Assessments list what the configured checks reported for each snapshot. They never
        include raw scanner output or secret values.
      </p>
    </div>
  );
}
