"use client";

import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "@/lib/cn";

/**
 * Dropdown menu on Radix primitives: focus management, arrow-key navigation,
 * Escape/outside dismissal, and Portal rendering. Meridian styling on top.
 */
export function Dropdown({
  label,
  trigger,
  children,
  align = "right",
  className,
}: {
  label: string;
  trigger: React.ReactNode;
  children: React.ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild aria-label={label}>
        <button type="button" className="group flex items-center gap-2 rounded-[10px] outline-none">
          {trigger}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align === "right" ? "end" : "start"}
          sideOffset={8}
          className={cn(
            "z-50 min-w-56 origin-top overflow-hidden rounded-xl border border-line bg-surface-1 p-1.5 shadow-pop",
            "data-[state=open]:animate-dropdown-in",
            className,
          )}
        >
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

const itemClass =
  "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium text-ink-2 outline-none transition-colors duration-150 data-[highlighted]:bg-surface-2 data-[highlighted]:text-ink";

export function DropdownItem({
  className,
  children,
  onSelect,
  disabled,
}: {
  className?: string;
  children: React.ReactNode;
  onSelect?: (event: Event) => void;
  disabled?: boolean;
}) {
  return (
    <DropdownMenu.Item onSelect={onSelect} disabled={disabled} className={cn(itemClass, className)}>
      {children}
    </DropdownMenu.Item>
  );
}

/** Wrap a Next.js Link so it behaves as a menu item. */
export function DropdownLink({
  className,
  children,
  ...rest
}: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <DropdownMenu.Item asChild>
      <a className={cn(itemClass, className)} {...rest}>
        {children}
      </a>
    </DropdownMenu.Item>
  );
}

export function DropdownSeparator({ className }: { className?: string }) {
  return <DropdownMenu.Separator className={cn("mx-2 my-1.5 h-px bg-line/70", className)} />;
}

export function DropdownLabel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={cn("px-3 pt-1.5 pb-1 font-mono text-[11px] font-medium tracking-[0.12em] text-ink-3 uppercase", className)}>
      {children}
    </p>
  );
}
