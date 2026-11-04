"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronDown, LogOut } from "lucide-react";
import { listWorkspaces } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { useAuth } from "@/components/auth/AuthContext";
import { MeridianLogo } from "@/components/brand/Logo";
import { Dropdown, DropdownItem, DropdownLabel, DropdownLink, DropdownSeparator } from "@/components/ui/Dropdown";
import { HealthBadge } from "./HealthBadge";
import { ThemeToggle } from "./ThemeToggle";

function WorkspaceSwitcher() {
  const [items, setItems] = React.useState<Workspace[] | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { items: workspaces } = await listWorkspaces();
        if (!cancelled) setItems(workspaces);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Dropdown
      label="Switch workspace"
      trigger={
        <span className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink-2 shadow-[inset_0_1px_0_rgb(255_255_255/0.4)] transition-all duration-200 hover:border-line-strong hover:text-ink dark:shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]">
          Workspaces
          <ChevronDown aria-hidden="true" className="size-3.5 opacity-70 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </span>
      }
    >
      <DropdownLabel>Workspaces</DropdownLabel>
      {items === null && !failed && (
        <p className="px-3 py-2 text-[13px] text-ink-3">Loading…</p>
      )}
      {failed && (
        <p className="px-3 py-2 text-[13px] text-ink-3">
          Unavailable — the API is unreachable.
        </p>
      )}
      {items?.map((workspace) => (
        <DropdownLink key={workspace.id} href={`/app/workspaces/${workspace.id}`}>
          <span className="min-w-0 flex-1 truncate">{workspace.name}</span>
          <span className="shrink-0 font-mono text-[11px] text-ink-3">{workspace.role}</span>
        </DropdownLink>
      ))}
      {items && items.length === 0 && (
        <p className="px-3 py-2 text-[13px] text-ink-3">No workspaces yet.</p>
      )}
    </Dropdown>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [signingOut, setSigningOut] = React.useState(false);

  async function handleLogout() {
    setSigningOut(true);
    await logout();
    router.push("/login");
    router.refresh();
  }

  const initial = (user?.display_name ?? user?.email ?? "?").trim().charAt(0).toUpperCase();

  return (
    <Dropdown
      label="Account"
      trigger={
        <span className="inline-flex items-center gap-2 rounded-[10px] py-1 pr-1.5 pl-1 transition-colors duration-200 hover:bg-surface-2">
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-full bg-accent text-[13px] font-bold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.25)]"
          >
            {initial}
          </span>
          <span className="hidden max-w-40 truncate text-[13px] font-semibold text-ink md:block">
            {user?.display_name ?? user?.email ?? "Account"}
          </span>
          <ChevronDown aria-hidden="true" className="size-3.5 text-ink-3 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </span>
      }
    >
      <div className="border-b border-line/70 px-3 py-2.5">
        <p className="truncate text-[13px] font-semibold text-ink">
          {user?.display_name ?? "Account"}
        </p>
        <p className="truncate font-mono text-xs text-ink-3">{user?.email}</p>
      </div>
      <div className="flex items-center gap-2.5 px-3 py-2 text-[13px] text-ink-2">
        <Check aria-hidden="true" className="size-3.5 text-success" />
        Signed in
      </div>
      <DropdownSeparator />
      <DropdownItem onSelect={() => void handleLogout()} disabled={signingOut}>
        <LogOut aria-hidden="true" className="size-4" />
        {signingOut ? "Signing out…" : "Sign out"}
      </DropdownItem>
    </Dropdown>
  );
}

export function Topbar() {
  return (
    <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-3 border-b border-line/70 bg-canvas/85 px-4 backdrop-blur-xl sm:px-6">
      <Link href="/app" aria-label="Meridian home" className="rounded-lg outline-none">
        <MeridianLogo markSize={26} />
      </Link>
      <div className="ml-auto flex items-center gap-2 sm:gap-2.5">
        <WorkspaceSwitcher />
        <ThemeToggle />
        <HealthBadge />
        <span aria-hidden="true" className="hidden h-6 w-px bg-line sm:block" />
        <UserMenu />
      </div>
    </header>
  );
}
