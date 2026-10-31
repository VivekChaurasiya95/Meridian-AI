"use client";

import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input, type InputProps } from "./Input";

export type PasswordInputProps = Omit<InputProps, "type" | "trailing">;

/** Password field with a show/hide toggle in its trailing edge. */
export const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ label, ...rest }, ref) => {
    const [visible, setVisible] = React.useState(false);
    const toggleLabel = `${visible ? "Hide" : "Show"} ${label}`;
    return (
      <Input
        ref={ref}
        label={label}
        type={visible ? "text" : "password"}
        trailing={
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            aria-label={toggleLabel}
            aria-pressed={visible}
            title={toggleLabel}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-[10px] text-ink-3 transition-colors hover:text-accent"
          >
            {visible ? (
              <EyeOff aria-hidden="true" className="size-4" />
            ) : (
              <Eye aria-hidden="true" className="size-4" />
            )}
          </button>
        }
        {...rest}
      />
    );
  },
);
PasswordInput.displayName = "PasswordInput";
