"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  MeridianApiError,
  formatTimestamp,
  getSecurityAssessment,
  listAssessmentFindings,
} from "@/lib/api";
import type {
  SecurityAssessment,
  SecurityAssessmentStatus,
  SecurityFinding,
  SecurityFindingScanner,
  SecurityFindingSeverity,
} from "@/lib/types";

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

const SEVERITY_TONE: Record<SecurityFindingSeverity, "danger" | "warning" | "neutral" | "info"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "neutral",
  informational: "info",
};

const SEVERITIES: SecurityFindingSeverity[] = ["critical", "high", "medium", "low", "informational"];
const SCANNERS: SecurityFindingScanner[] = ["semgrep", "gitleaks"];

function FindingCard({ finding }: { finding: SecurityFinding }) {
  const { location, evidence } = finding;
  const lineLabel =
    location.start_line !== null && location.end_line !== null
      ? location.start_line === location.end_line
        ? `line ${location.start_line}`
        : `lines ${location.start_line}–${location.end_line}`
      : null;
  return (
    <li>
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={SEVERITY_TONE[finding.severity]} dot={false}>
            {finding.severity}
          </Badge>
          <Badge tone="neutral" dot={false}>
            {finding.scanner}
          </Badge>
          <span className="text-[14px] font-semibold">{finding.title}</span>
          <span className="ml-auto font-mono text-[11px] text-ink-3">
            {finding.rule_id} · {finding.confidence} confidence
          </span>
        </div>
        {finding.description !== "" && (
          <p className="text-[13px] text-ink-2">{finding.description}</p>
        )}
        <p className="truncate font-mono text-xs text-ink-3" title={location.path}>
          {location.path}
          {lineLabel !== null && ` · ${lineLabel}`}
        </p>
        {evidence.excerpt !== null && evidence.excerpt !== "" && (
          <pre className="overflow-x-auto rounded-lg border border-line/60 bg-surface-2/60 p-2.5 font-mono text-xs text-ink-2">
            {evidence.excerpt}
          </pre>
        )}
        <p className="font-mono text-[11px] text-ink-3">
          category {finding.category}
          {evidence.redacted && " · excerpt masked"}
          {evidence.truncated && " · excerpt truncated"}
        </p>
      </Card>
    </li>
  );
}

export default function AssessmentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const [assessment, setAssessment] = React.useState<SecurityAssessment | null>(null);
  const [findings, setFindings] = React.useState<SecurityFinding[] | null>(null);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [severity, setSeverity] = React.useState<SecurityFindingSeverity | null>(null);
  const [scanner, setScanner] = React.useState<SecurityFindingScanner | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [findingsError, setFindingsError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const row = await getSecurityAssessment(id);
        if (cancelled) return;
        setAssessment(row);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push(`/login?next=${encodeURIComponent(`/app/security-assessments/${id}`)}`);
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this assessment.");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id, router]);

  const loadFindings = React.useCallback(
    async (cursor: string | null, append: boolean) => {
      try {
        const page = await listAssessmentFindings(id, {
          cursor,
          severity,
          scanner,
        });
        setFindings((current) =>
          append ? [...(current ?? []), ...page.items] : page.items,
        );
        setNextCursor(page.page.next_cursor);
        setFindingsError(null);
        return true;
      } catch (err) {
        setFindingsError(err instanceof Error ? err.message : "Could not load findings.");
        return false;
      }
    },
    [id, severity, scanner],
  );

  React.useEffect(() => {
    setFindings(null);
    setNextCursor(null);
    void loadFindings(null, false);
  }, [loadFindings]);

  async function handleLoadMore() {
    if (nextCursor === null) return;
    setLoadingMore(true);
    await loadFindings(nextCursor, true);
    setLoadingMore(false);
  }

  if (error !== null) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10 sm:px-6">
        <Alert tone="danger" title="Not available">
          {error}
        </Alert>
        <Link href="/app/projects" className="text-[13px] font-semibold text-accent">
          Back to projects
        </Link>
      </div>
    );
  }

  if (assessment === null) {
    return (
      <div
        className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-10 sm:px-6"
        aria-label="Loading assessment"
      >
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const total = assessment.summary?.total ?? 0;
  const bySeverity = assessment.summary?.by_severity ?? {};
  const scannerEntries = Object.entries(assessment.scanner_versions ?? {});

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-10 sm:px-6">
      <div>
        <Link
          href={`/app/projects/${assessment.project_id}?tab=security`}
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-3 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to project
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-display text-[28px] leading-tight font-semibold tracking-[-0.01em]">
            Assessment
          </h1>
          <Badge tone={STATUS_TONE[assessment.status]} dot={false}>
            {assessment.status.replace(/_/g, " ")}
          </Badge>
        </div>
        <p className="mt-1 font-mono text-xs text-ink-3">
          recorded {formatTimestamp(assessment.created_at)} · generation {assessment.generation} ·
          policy {assessment.policy_version} · ruleset {assessment.ruleset_version}
        </p>
      </div>

      <Card className="flex flex-col gap-2 p-4">
        <h2 className="text-[15px] font-semibold">Outcome</h2>
        <p className="text-[13px] text-ink-2">
          {total === 0
            ? "No issues detected by configured checks."
            : `${total} ${total === 1 ? "finding" : "findings"} detected by configured checks.`}
        </p>
        {Object.keys(bySeverity).length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Findings by severity">
            {Object.entries(bySeverity).map(([level, count]) => (
              <Badge key={level} tone="neutral" dot={false}>
                {level}: {count}
              </Badge>
            ))}
          </div>
        )}
        {scannerEntries.length > 0 && (
          <p className="font-mono text-[11px] text-ink-3">
            {scannerEntries.map(([name, version]) => `${name} ${version}`).join(" · ")}
          </p>
        )}
        <p className="truncate font-mono text-[11px] text-ink-3">
          snapshot {assessment.snapshot_id}
        </p>
      </Card>

      <section aria-label="Findings">
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="text-[15px] font-semibold">
            Findings {findings !== null && findings.length > 0 && `(${findings.length})`}
          </h2>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2.5">
          <label className="flex items-center gap-2 text-[13px] text-ink-3">
            Severity
            <select
              value={severity ?? ""}
              onChange={(event) =>
                setSeverity((event.target.value || null) as SecurityFindingSeverity | null)
              }
              className="h-9 rounded-[10px] border border-line bg-surface-1 px-2.5 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
            >
              <option value="">All</option>
              {SEVERITIES.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-[13px] text-ink-3">
            Scanner
            <select
              value={scanner ?? ""}
              onChange={(event) =>
                setScanner((event.target.value || null) as SecurityFindingScanner | null)
              }
              className="h-9 rounded-[10px] border border-line bg-surface-1 px-2.5 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
            >
              <option value="">All</option>
              {SCANNERS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {findingsError !== null && (
          <div className="mb-2">
            <Alert tone="danger" title="Findings unavailable">
              {findingsError}
            </Alert>
          </div>
        )}

        {findings === null ? (
          <Skeleton className="h-24" />
        ) : findings.length === 0 ? (
          <Alert tone="info" title="No findings on this page">
            {severity !== null || scanner !== null
              ? "Nothing matches these filters — clear them to see every finding."
              : "No issues detected by configured checks."}
          </Alert>
        ) : (
          <div className="flex flex-col gap-3">
            <ol className="flex flex-col gap-2">
              {findings.map((finding) => (
                <FindingCard key={finding.id} finding={finding} />
              ))}
            </ol>
            {nextCursor !== null && (
              <div>
                <Button variant="secondary" onClick={() => void handleLoadMore()} loading={loadingMore}>
                  Load more
                </Button>
              </div>
            )}
          </div>
        )}
      </section>

      <p className="text-[12px] leading-5 text-ink-3">
        Findings come only from the configured checks, with excerpts masked at collection time.
        The absence of findings does not mean the code is free of all possible issues.
      </p>
    </div>
  );
}
