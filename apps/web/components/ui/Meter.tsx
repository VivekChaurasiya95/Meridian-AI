"use client";

import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";

/**
 * Progress meter whose bar fills when scrolled into view. Renders the final
 * width statically under reduced motion. Exposes a real progressbar role.
 */
export function Meter({
  value,
  label = "Progress",
  className,
  barClassName,
}: {
  /** Fill percentage, 0–100. */
  value: number;
  label?: string;
  className?: string;
  barClassName?: string;
}) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.min(Math.max(value, 0), 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 overflow-hidden rounded-full bg-surface-3", className)}
    >
      {reduceMotion ? (
        <div
          className={cn("h-full rounded-full bg-sage", barClassName)}
          style={{ width: `${clamped}%` }}
        />
      ) : (
        <motion.div
          className={cn("h-full origin-left rounded-full bg-sage", barClassName)}
          style={{ width: `${clamped}%` }}
          initial={{ scaleX: 0 }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true, margin: "-64px" }}
          transition={{ duration: 1, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
        />
      )}
    </div>
  );
}
