"use client";

import { Card } from "@/components/ui/Card";

export interface ReportSectionRow {
  label: string;
  value: string;
  mono?: boolean;
}

/** Metadata section: a titled definition list inside a card (M10). */
export function ReportSection({ title, rows }: { title: string; rows: ReportSectionRow[] }) {
  return (
    <Card className="p-4">
      <h3 className="mb-2 text-[14px] font-semibold">{title}</h3>
      <dl className="flex flex-col gap-1.5">
        {rows.map((row) => (
          <div key={row.label} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
            <dt className="w-36 shrink-0 text-[13px] font-medium text-ink-3">{row.label}</dt>
            <dd
              className={
                row.mono
                  ? "min-w-0 flex-1 truncate font-mono text-[13px] text-ink"
                  : "min-w-0 flex-1 text-[13px] text-ink"
              }
              title={row.value}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
