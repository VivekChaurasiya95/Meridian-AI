"use client";

import * as React from "react";
import Link from "next/link";
import { MeridianApiError, formatTimestamp, getSnapshotAssessment } from "@/lib/api";
import type { SecurityAssessment } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";

type LoadState =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error"; message: string }
  | { status: "ready"; assessment: SecurityAssessment };

/**
 * Latest assessment for one snapshot. A 404 means no assessment has been
 * recorded yet — an honest empty state, not an error.
 */
export function SnapshotAssessment({ snapshotId }: { snapshotId: string }) {
  const [state, setState] = React.useState<LoadState>({ status: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const assessment = await getSnapshotAssessment(snapshotId);
        if (!cancelled) setState({ status: "ready", assessment });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 404) {
          setState({ status: "missing" });
        } else {
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Could not load the assessment.",
          });
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [snapshotId]);

  if (state.status === "loading") {
    return (
      <div aria-label="Loading assessment">
        <Skeleton className="h-16" />
      </div>
    );
  }

  if (state.status === "missing") {
    return (
      <p className="text-[13px] text-ink-3">
        No assessment recorded for this snapshot yet — checks run after storage completes.
      </p>
    );
  }

  if (state.status === "error") {
    return (
      <Alert tone="danger" title="Assessment unavailable">
        {state.message}
      </Alert>
    );
  }

  const { assessment } = state;
  const total = assessment.summary?.total ?? 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={assessment.status === "failed" ? "danger" : "neutral"} dot={false}>
        {assessment.status.replace(/_/g, " ")}
      </Badge>
      <span className="text-[13px] text-ink-2">
        {total === 0
          ? "No issues detected by configured checks."
          : `${total} ${total === 1 ? "finding" : "findings"} detected by configured checks.`}
      </span>
      <span className="font-mono text-[11px] text-ink-3">
        {formatTimestamp(assessment.created_at)}
      </span>
      <Link
        href={`/app/security-assessments/${assessment.id}`}
        className="ml-auto text-[13px] font-semibold text-accent hover:underline"
      >
        Open assessment
      </Link>
    </div>
  );
}
