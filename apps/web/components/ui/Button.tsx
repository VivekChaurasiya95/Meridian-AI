"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  [
    "group/btn relative inline-flex cursor-pointer items-center justify-center gap-2 overflow-hidden",
    "font-medium whitespace-nowrap transition-all duration-200 ease-out",
    "outline-none select-none",
    "focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_45%,transparent)]",
    "active:scale-[0.98]",
    "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-55 disabled:shadow-none disabled:saturate-50",
  ],
  {
    variants: {
      variant: {
        primary: [
          "bg-accent text-accent-ink font-semibold",
          "shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_1px_2px_rgb(64_45_20/0.2),0_10px_24px_-10px_var(--color-accent)]",
          "hover:bg-accent-hover hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_1px_2px_rgb(64_45_20/0.2),0_14px_28px_-10px_var(--color-accent)]",
          "active:bg-accent-pressed",
        ],
        secondary: [
          "border border-line bg-surface-1 text-ink",
          "shadow-[inset_0_1px_0_rgb(255_255_255/0.5),0_1px_2px_rgb(64_45_20/0.08)]",
          "dark:shadow-[inset_0_1px_0_rgb(255_255_255/0.06),0_1px_2px_rgb(0_0_0/0.3)]",
          "hover:border-line-strong hover:bg-surface-2",
          "active:bg-surface-3",
        ],
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink active:bg-surface-3",
        danger: [
          "border border-danger/35 bg-danger/12 text-danger",
          "hover:bg-danger/20 active:bg-danger/25",
        ],
      },
      size: {
        sm: "h-8 rounded-md px-3 text-[13px]",
        md: "h-10 rounded-[10px] px-4 text-sm",
        lg: "h-12 rounded-xl px-6 text-[15px]",
        icon: "size-9 rounded-[10px]",
        "icon-sm": "size-8 rounded-md",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant, size, loading = false, className, disabled, children, ...rest }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...rest}
    >
      {/* Sheen sweep on hover for filled buttons */}
      {variant === "primary" && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/3 -skew-x-12 bg-white/20 blur-md transition-transform duration-500 ease-out group-hover/btn:translate-x-[420%]"
        />
      )}
      {loading && (
        <svg className="size-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      )}
      <span className="relative inline-flex items-center gap-2">{children}</span>
    </button>
  ),
);
Button.displayName = "Button";

export { buttonVariants };
