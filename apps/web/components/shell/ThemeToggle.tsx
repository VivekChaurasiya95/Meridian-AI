"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/cn";

/** Light/dark toggle with a rotating icon swap. Placeholder until mounted. */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const reduceMotion = useReducedMotion();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <span
        aria-hidden="true"
        className={cn(
          "flex size-9 items-center justify-center rounded-[10px] border border-line bg-surface-1",
          className,
        )}
      />
    );
  }

  const isDark = resolvedTheme !== "light";
  const Icon = isDark ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={cn(
        "relative flex size-9 cursor-pointer items-center justify-center overflow-hidden rounded-[10px] border border-line bg-surface-1 text-ink-2 shadow-[inset_0_1px_0_rgb(255_255_255/0.4)] transition-all duration-200 outline-none",
        "dark:shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]",
        "hover:border-line-strong hover:text-accent active:scale-95",
        "focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_40%,transparent)]",
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={isDark ? "sun" : "moon"}
          initial={reduceMotion ? false : { rotate: -120, opacity: 0, scale: 0.5 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={reduceMotion ? undefined : { rotate: 120, opacity: 0, scale: 0.5 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="flex"
        >
          <Icon aria-hidden="true" className="size-[17px]" />
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
