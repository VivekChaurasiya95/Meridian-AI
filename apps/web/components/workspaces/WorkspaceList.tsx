"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import type { Workspace } from "@/lib/types";
import { formatTimestamp } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent } from "@/components/ui/Card";

const LIST: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
};

const ITEM: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] } },
};

export function WorkspaceList({ items }: { items: Workspace[] }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.ul
      className="flex flex-col gap-3"
      aria-label="Workspaces"
      initial={reduceMotion ? false : "hidden"}
      animate="show"
      variants={reduceMotion ? undefined : LIST}
    >
      {items.map((workspace) => (
        <motion.li key={workspace.id} variants={reduceMotion ? undefined : ITEM} layout={!reduceMotion}>
          <Link
            href={`/app/workspaces/${workspace.id}`}
            className="group block rounded-xl outline-none focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_45%,transparent)]"
          >
            <Card interactive>
              <CardContent className="flex items-center gap-4">
                <span
                  aria-hidden="true"
                  className="font-display flex size-10 shrink-0 items-center justify-center rounded-xl bg-sage-subtle text-[17px] font-semibold text-sage"
                >
                  {workspace.name.trim().charAt(0).toUpperCase() || "?"}
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate font-medium text-ink">{workspace.name}</span>
                  <span className="truncate font-mono text-xs text-ink-3">
                    {workspace.slug} · created {formatTimestamp(workspace.created_at)}
                  </span>
                </span>
                <Badge tone={workspace.role === "owner" || workspace.role === "admin" ? "accent" : "neutral"}>
                  {workspace.role}
                </Badge>
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-ink-3 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-sage"
                />
              </CardContent>
            </Card>
          </Link>
        </motion.li>
      ))}
    </motion.ul>
  );
}
