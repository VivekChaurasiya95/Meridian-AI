"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { MeridianApiError, formatTimestamp, getLatestInvestigationReport } from "@/lib/api";
import type { InvestigationReport } from "@/lib/types";

/** Latest narrative report for the investigation (M9). Hidden until one exists. */
export function LatestReportCard({ investigationId }: { investigationId: string }) {
  const [report, setReport] = React.useState<InvestigationReport | null>(null);
  const [missing, setMissing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setReport(await getLatestInvestigationReport(investigationId));
      setError(null);
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 404) {
        setMissing(true);
        return;
      }
      setError(err instanceof Error ? err.message : "Could not load the report.");
    }
  }, [investigationId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  if (missing) return null;

  if (error !== null && report === null) {
    return (
      <section aria-label="Latest report">
        <h2 className="mb-2 text-[15px] font-semibold">Report</h2>
        <Alert tone="danger" title="Report unavailable">
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

  if (report === null) {
    return (
      <section aria-label="Latest report">
        <h2 className="mb-2 text-[15px] font-semibold">Report</h2>
        <Skeleton className="h-24" />
      </section>
    );
  }

  return (
    <section aria-label="Latest report">
      <h2 className="mb-2 text-[15px] font-semibold">Report</h2>
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-[14px] font-semibold">{report.title}</span>
          <span className="font-mono text-[11px] text-ink-3">
            {report.model} · {formatTimestamp(report.created_at)}
          </span>
        </div>
        <p className="text-[13px] text-ink-2">{report.summary}</p>
        {report.sections.length > 0 && (
          <div>
            <Button size="sm" variant="secondary" onClick={() => setOpen((value) => !value)}>
              {open ? "Hide sections" : `Show sections (${report.sections.length})`}
            </Button>
          </div>
        )}
        {open && (
          <div className="flex flex-col gap-3 border-t border-line pt-3">
            {report.sections.map((section) => (
              <div key={section.heading}>
                <h3 className="text-[13px] font-semibold">{section.heading}</h3>
                <p className="mt-0.5 text-[13px] text-ink-2">{section.body}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </section>
  );
}
