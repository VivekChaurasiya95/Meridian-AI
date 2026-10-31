"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/cn";

/**
 * Restrained scroll reveal for major sections only: a soft rise with a hint
 * of blur, played once when the block enters the viewport. Renders statically
 * when the user prefers reduced motion.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  /** Stagger delay in seconds. */
  delay?: number;
  as?: "div" | "section" | "li" | "figure" | "span";
}) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) {
    const Tag = as;
    return <Tag className={className}>{children}</Tag>;
  }
  const components = {
    div: motion.div,
    section: motion.section,
    li: motion.li,
    figure: motion.figure,
    span: motion.span,
  } as const;
  const Tag = components[as];
  return (
    <Tag
      className={cn(className)}
      initial={{ opacity: 0, y: 22, filter: "blur(4px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, margin: "-64px" }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </Tag>
  );
}
