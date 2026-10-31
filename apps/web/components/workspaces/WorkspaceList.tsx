"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Workspace } from "@/lib/types";
import { formatTimestamp } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent } from "@/components/ui/Card";

export function WorkspaceList({ items }: { items: Workspace[] }) {
  return (
    <ul className="flex flex-col gap-3" aria-label="Workspaces">
      {items.map((workspace) => (
        <li key={workspace.id}>
          <Link
            href={`/app/workspaces/${workspace.id}`}
            className="group block rounded-xl focus-visible:outline-none"
          >
            <Card interactive>
              <CardContent className="flex items-center gap-4">
                <span
                  aria-hidden="true"
                  className="font-display flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-subtle text-[17px] font-semibold text-accent"
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
                  className="size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-0.5"
                />
              </CardContent>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
