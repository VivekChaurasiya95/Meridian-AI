"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderKanban, LayoutDashboard, FileText, FlaskConical, Settings } from "lucide-react";
import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/Badge";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  available: boolean;
  milestone?: string;
}

const NAV: NavItem[] = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, available: true },
  { href: "/app/projects", label: "Projects", icon: FolderKanban, available: false, milestone: "M3" },
  { href: "/app/investigations", label: "Investigations", icon: FlaskConical, available: false, milestone: "M4" },
  { href: "/app/reports", label: "Reports", icon: FileText, available: false, milestone: "M10" },
  { href: "/app/settings", label: "Settings", icon: Settings, available: false, milestone: "M2" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex w-64 shrink-0 flex-col gap-1 px-3 py-5 max-lg:hidden">
      <p className="px-3 pb-2 font-mono text-[11px] font-medium tracking-[0.14em] text-ink-3 uppercase">
        Workspace
      </p>
      {NAV.map((item) => {
        const active = item.available && (item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href));
        const Glyph = item.icon;
        const content = (
          <>
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-200",
                active ? "bg-accent text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.25)]" : "bg-surface-2 text-ink-3",
              )}
            >
              <Glyph aria-hidden="true" className="size-4" />
            </span>
            <span className="flex-1 truncate">{item.label}</span>
            {!item.available && item.milestone && (
              <Badge tone="neutral" dot={false} className="px-1.5 text-[11px]">
                {item.milestone}
              </Badge>
            )}
            {active && <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-accent" />}
          </>
        );
        const classes = cn(
          "relative flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[13px] font-semibold transition-all duration-200",
          active ? "bg-surface-1 text-ink shadow-card ring-1 ring-line/60" : "text-ink-2",
          item.available ? "hover:bg-surface-1 hover:text-ink hover:shadow-card" : "cursor-not-allowed opacity-55",
        );
        return item.available ? (
          <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={classes}>
            {content}
          </Link>
        ) : (
          <span key={item.href} className={classes} title={`Arrives in ${item.milestone}`} aria-disabled="true">
            {content}
          </span>
        );
      })}
      <div className="mt-auto px-1 pt-4">
        <div className="rounded-xl border border-line/70 bg-surface-1 p-3.5 shadow-card">
          <p className="font-mono text-[11px] font-medium tracking-[0.12em] text-sage uppercase">Milestone 2</p>
          <p className="mt-1 text-xs leading-5 text-ink-2">
            Auth & workspaces live. Unbuilt areas are marked, never faked.
          </p>
        </div>
      </div>
    </nav>
  );
}

/** Compact horizontal nav for narrow screens (the sidebar is desktop-only). */
export function MobileNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Sections"
      className="flex gap-1.5 overflow-x-auto border-b border-line/70 bg-canvas/90 px-3 py-2.5 no-scrollbar lg:hidden"
    >
      {NAV.filter((item) => item.available).map((item) => {
        const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
        const Glyph = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-[10px] px-3 py-2 text-[13px] font-semibold transition-colors duration-200",
              active ? "bg-surface-1 text-ink shadow-card ring-1 ring-line/60" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            <Glyph aria-hidden="true" className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
