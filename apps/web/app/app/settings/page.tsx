"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { Check, Moon, Sun } from "lucide-react";
import { MeridianApiError, getWorkspace, listWorkspaces } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { useAuth } from "@/components/auth/AuthContext";
import { ProfileCard } from "@/components/settings/ProfileCard";
import { MembersCard } from "@/components/workspaces/MembersCard";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

function AppearanceCard() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const options = [
    { value: "light", label: "Light", hint: "Sage-tinted bone studio", Icon: Sun },
    { value: "dark", label: "Dark", hint: "Green-ink night", Icon: Moon },
  ] as const;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Your theme, applied immediately and remembered.</CardDescription>
      </CardHeader>
      <CardContent>
        {!mounted ? (
          <div className="flex flex-col gap-2 sm:flex-row" aria-label="Loading theme">
            <Skeleton className="h-16 flex-1" />
            <Skeleton className="h-16 flex-1" />
          </div>
        ) : (
          <fieldset className="flex flex-col gap-2 sm:flex-row">
            <legend className="sr-only">Theme</legend>
            {options.map(({ value, label, hint, Icon }) => (
              <label
                key={value}
                className={cn(
                  "flex flex-1 cursor-pointer items-center gap-3 rounded-xl border px-4 py-3.5 transition-all duration-200",
                  "has-checked:border-accent has-checked:bg-surface-2 has-checked:shadow-card",
                  "has-focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_38%,transparent)]",
                  "border-line bg-surface-1 hover:border-line-strong hover:bg-surface-2",
                )}
              >
                <input
                  type="radio"
                  name="theme"
                  value={value}
                  checked={resolvedTheme === value}
                  onChange={() => setTheme(value)}
                  className="sr-only"
                />
                <span
                  aria-hidden="true"
                  className="flex size-9 shrink-0 items-center justify-center rounded-[10px] border border-line bg-surface-1 text-ink-2"
                >
                  <Icon className="size-[17px]" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14px] font-semibold text-ink">{label}</span>
                  <span className="block truncate text-[12px] text-ink-3">{hint}</span>
                </span>
                {resolvedTheme === value && (
                  <Check aria-hidden="true" className="size-4 shrink-0 text-sage" />
                )}
              </label>
            ))}
          </fieldset>
        )}
        <p className="mt-3 text-[12px] leading-5 text-ink-3">
          You can also switch from the header toggle on any screen.
        </p>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");
  const { user } = useAuth();

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [workspace, setWorkspace] = React.useState<Workspace | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    async function boot() {
      try {
        const { items: list } = await listWorkspaces(100);
        if (cancelled) return;
        setWorkspaces(list);
        if (workspaceParam) setWorkspaceId(workspaceParam);
        else if (list.length > 0) setWorkspaceId(list[0].id);
        else setLoading(false);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fsettings");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load workspaces.");
        setLoading(false);
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [router, workspaceParam]);

  React.useEffect(() => {
    if (!workspaceId) {
      setWorkspace(null);
      return;
    }
    let cancelled = false;
    async function loadWorkspace() {
      setLoading(true);
      try {
        const row = await getWorkspace(workspaceId as string);
        if (cancelled) return;
        setWorkspace(row);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fsettings");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load the workspace.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, router, reloadKey]);

  if (loading && workspace === null && error === null) {
    return (
      <div className="flex max-w-3xl flex-col gap-6" aria-label="Loading settings">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  const canManage = workspace !== null && (workspace.role === "owner" || workspace.role === "admin");

  return (
    <div className="flex max-w-3xl animate-fade-in flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-sage uppercase">
            Settings
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">
            Workspace settings
          </h1>
          <p className="mt-1.5 text-[15px] text-ink-2">
            Your profile, appearance, and this workspace&apos;s membership.
          </p>
        </div>
        {workspaces && workspaces.length > 0 && (
          <label className="flex items-center gap-2 text-[13px] text-ink-3">
            Workspace
            <select
              value={workspaceId ?? ""}
              onChange={(event) => {
                setWorkspaceId(event.target.value);
                router.replace(`/app/settings?workspace=${event.target.value}`);
              }}
              className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
            >
              {workspaces.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error !== null && (
        <div className="flex flex-col gap-2">
          <Alert tone="danger" title="Settings unavailable">
            {error}
          </Alert>
          <div>
            <Button size="sm" variant="secondary" onClick={() => setReloadKey((key) => key + 1)}>
              Retry
            </Button>
          </div>
        </div>
      )}

      <ProfileCard />

      <AppearanceCard />

      {workspaces !== null && workspaces.length === 0 && error === null && (
        <Alert tone="info" title="Create a workspace first">
          Membership settings live inside a workspace.{" "}
          <Link href="/app" className="font-semibold underline">
            Back to overview
          </Link>
        </Alert>
      )}

      {workspace !== null && (
        <>
          <MembersCard
            workspaceId={workspace.id}
            canManage={canManage}
            currentUserId={user?.id ?? ""}
          />
          <p className="text-[13px] text-ink-3">
            To rename this workspace,{" "}
            <Link
              href={`/app/workspaces/${workspace.id}`}
              className="font-semibold text-accent hover:underline"
            >
              open its workspace page
            </Link>
            .
          </p>
        </>
      )}
    </div>
  );
}
