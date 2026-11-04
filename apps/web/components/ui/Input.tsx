"use client";

import * as React from "react";
import { cn } from "@/lib/cn";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | null;
  hint?: string;
  /** Optional control rendered inside the field's trailing edge (e.g. a toggle). */
  trailing?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, trailing, id, className, ...rest }, ref) => {
    const generatedId = React.useId();
    const inputId = id ?? generatedId;
    const errorId = `${inputId}-error`;
    const hintId = `${inputId}-hint`;
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={inputId} className="text-[13px] font-semibold text-ink">
          {label}
        </label>
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={cn(error && errorId, hint && hintId) || undefined}
            className={cn(
              "h-10 w-full rounded-[10px] border bg-surface-1 px-3.5 text-ink shadow-[inset_0_1px_2px_rgb(64_45_20/0.06)] transition-all duration-200 outline-none placeholder:text-ink-3",
              "hover:border-line-strong",
              "focus:border-accent focus:bg-inset focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_22%,transparent)]",
              trailing && "pr-10",
              error
                ? "border-danger focus:border-danger focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-danger)_22%,transparent)]"
                : "border-line",
              className,
            )}
            {...rest}
          />
          {trailing}
        </div>
        {error ? (
          <p id={errorId} role="alert" className="animate-alert-in text-[13px] font-medium text-danger">
            {error}
          </p>
        ) : hint ? (
          <p id={hintId} className="text-[13px] text-ink-3">
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);
Input.displayName = "Input";
