import * as React from "react";
import { AlertTriangle, Info, OctagonX, CircleCheck } from "lucide-react";
import { cn } from "@/lib/cn";

export type AlertTone = "info" | "success" | "warning" | "danger";

const toneClass: Record<AlertTone, string> = {
  info: "border-info/30 bg-info/10",
  success: "border-success/30 bg-success/10",
  warning: "border-warning/30 bg-warning/10",
  danger: "border-danger/30 bg-danger/10",
};

const iconTone: Record<AlertTone, string> = {
  info: "bg-info/15 text-info",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
};

const Icon: Record<AlertTone, typeof Info> = {
  info: Info,
  success: CircleCheck,
  warning: AlertTriangle,
  danger: OctagonX,
};

export function Alert({
  tone = "info",
  title,
  className,
  children,
}: {
  tone?: AlertTone;
  title: string;
  className?: string;
  children?: React.ReactNode;
}) {
  const Glyph = Icon[tone];
  return (
    <div role="alert" className={cn("flex animate-alert-in gap-3 rounded-xl border px-4 py-3.5 shadow-card", toneClass[tone], className)}>
      <span aria-hidden="true" className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", iconTone[tone])}>
        <Glyph className="size-4" />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {children ? <div className="text-[13px] leading-5 text-ink-2">{children}</div> : null}
      </div>
    </div>
  );
}
