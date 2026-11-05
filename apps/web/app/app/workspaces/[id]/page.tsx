"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, FolderKanban } from "lucide-react";
import { MeridianApiError, formatTimestamp, getWorkspace, updateWorkspace } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { useAuth } from "@/components/auth/AuthContext";
import { MembersCard } from "@/components/workspaces/MembersCard";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

type LoadState =
  | { status: "loading" }
  | { status: "not_found" }
  | { status: "error"; message: string }
  | { status: "ready"; workspace: Workspace };

function MetadataRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-line/60 py-2.5 last:border-0">
      <dt className="shrink-0 text-[13px] text-ink-3">{label}</dt>
      <dd className={`truncate text-right text-[13px] ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

export default function WorkspaceDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const { user } = useAuth();
  const toast = useToast();
  const [state, setState] = React.useState<LoadState>({ status: "loading" });
  const [name, setName] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const workspace = await getWorkspace(id);
        if (cancelled) return;
        setState({ status: "ready", workspace });
        setName(workspace.name);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push(`/login?next=${encodeURIComponent(`/app/workspaces/${id}`)}`);
        } else if (err instanceof MeridianApiError && err.status === 404) {
          setState({ status: "not_found" });
        } else {
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Could not load the workspace.",
          });
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id, router]);

  async function handleRename(event: React.FormEvent) {
    event.preventDefault();
    if (state.status !== "ready" || !name.trim() || name.trim() === state.workspace.name) return;
    setSaving(true);
    setSaveError(null);
    try {
      const workspace = await updateWorkspace(id, { name: name.trim() });
      setState({ status: "ready", workspace });
      toast.success(`Workspace renamed to “${workspace.name}”.`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not rename the workspace.");
    } finally {
      setSaving(false);
    }
  }

  if (state.status === "loading") {
    return (
      <div className="flex max-w-3xl flex-col gap-6" aria-label="Loading workspace">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        <Alert tone="warning" title="Workspace not found">
          It may have been deleted, or the address is wrong.
        </Alert>
        <div>
          <Link href="/app" className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface-1 px-3 text-[13px] hover:border-line-strong">
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to overview
          </Link>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        <Alert tone="danger" title="Could not load the workspace">{state.message}</Alert>
        <div>
          <Link href="/app" className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface-1 px-3 text-[13px] hover:border-line-strong">
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to overview
          </Link>
        </div>
      </div>
    );
  }

  const { workspace } = state;
  const canManage = workspace.role === "owner" || workspace.role === "admin";

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <Link href="/app" className="group inline-flex items-center gap-1.5 font-mono text-xs font-medium tracking-wide text-ink-3 uppercase transition-colors hover:text-accent">
          <ArrowLeft aria-hidden="true" className="size-3.5 transition-transform duration-200 group-hover:-translate-x-0.5" /> Overview
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-display text-[32px] leading-9 font-semibold tracking-tight">{workspace.name}</h1>
          <Badge tone={canManage ? "accent" : "neutral"}>{workspace.role}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Workspace</CardTitle>
          <CardDescription>Persisted metadata for this workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl>
            <MetadataRow label="Name" value={workspace.name} />
            <MetadataRow label="Slug" value={workspace.slug} mono />
            <MetadataRow label="ID" value={workspace.id} mono />
            <MetadataRow label="Your role" value={workspace.role} />
            <MetadataRow label="Created" value={formatTimestamp(workspace.created_at)} />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rename</CardTitle>
          <CardDescription>Owners and admins can rename the workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          {canManage ? (
            <form onSubmit={handleRename} className="flex flex-col gap-4">
              {saveError && <Alert tone="danger" title="Could not rename">{saveError}</Alert>}
              <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
              <div>
                <Button type="submit" variant="secondary" loading={saving} disabled={!name.trim() || name.trim() === workspace.name}>
                  Save changes
                </Button>
              </div>
            </form>
          ) : (
            <p className="text-[13px] text-ink-2">Your role ({workspace.role}) cannot rename this workspace.</p>
          )}
        </CardContent>
      </Card>

      <MembersCard workspaceId={id} canManage={canManage} currentUserId={user?.id ?? ""} />

      <Card>
        <CardHeader>
          <CardTitle>Projects</CardTitle>
          <CardDescription>Codebases under investigation in this workspace.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-2">
            <FolderKanban aria-hidden="true" className="size-5 text-accent" />
          </span>
          <div>
            <p className="font-medium">Manage this workspace&apos;s codebases</p>
            <p className="mt-1 text-[13px] text-ink-2">
              Upload ZIP archives, inspect stacks, and browse immutable snapshots.
            </p>
          </div>
          <Link href={`/app/projects?workspace=${id}`}>
            <Button variant="secondary">View projects</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
