import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap tracking-wide",
  {
    variants: {
      tone: {
        neutral: "border-line bg-surface-2 text-ink-2",
        accent: "border-accent/30 bg-accent-subtle text-accent",
        success: "border-success/30 bg-success/12 text-success",
        warning: "border-warning/30 bg-warning/12 text-warning",
        danger: "border-danger/30 bg-danger/12 text-danger",
        info: "border-info/30 bg-info/12 text-info",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

const dotClass: Record<string, string> = {
  neutral: "bg-neutral",
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

export function Badge({
  tone = "neutral",
  pulse = false,
  dot = true,
  className,
  children,
}: {
  tone?: BadgeTone;
  /** Animate the status dot (for live states). */
  pulse?: boolean;
  /** Hide the leading dot for plain labels. */
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span className={cn(badgeVariants({ tone }), className)}>
      {dot && (
        <span
          aria-hidden="true"
          className={cn("size-1.5 rounded-full", dotClass[tone], pulse && "animate-pulse-dot")}
        />
      )}
      {children}
    </span>
  );
}

export interface BadgeProps extends VariantProps<typeof badgeVariants> {}
