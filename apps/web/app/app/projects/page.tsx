"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Archive,
  ArchiveRestore,
  ArrowRight,
  FolderKanban,
  Plus,
  Search,
  Settings2,
  Trash2,
} from "lucide-react";
import {
  MeridianApiError,
  archiveProject,
  deleteProject,
  formatTimestamp,
  getProjectsSummary,
  listProjects,
  listWorkspaces,
  unarchiveProject,
  type ProjectSort,
  type ProjectStatusFilter,
} from "@/lib/api";
import type { Project, ProjectsSummary, Workspace } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownLink,
  DropdownSeparator,
} from "@/components/ui/Dropdown";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

type LoadState =
  | { status: "loading" }
  | { status: "no-workspace" }
  | { status: "error"; message: string }
  | { status: "ready" };

const STATUS_FILTERS: { key: ProjectStatusFilter | null; label: string }[] = [
  { key: null, label: "All" },
  { key: "active", label: "Active" },
  { key: "archived", label: "Archived" },
];

const SORTS: { key: ProjectSort; label: string }[] = [
  { key: "updated", label: "Recently updated" },
  { key: "created", label: "Recently created" },
  { key: "name", label: "Name" },
];

function statusTone(status: Project["status"]): "accent" | "neutral" | "warning" {
  if (status === "active") return "accent";
  if (status === "archived") return "neutral";
  return "warning";
}

function MetricCard({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-xl border border-line/70 bg-surface-1 px-4 py-3.5 shadow-card">
      <p className="font-mono text-[11px] font-medium tracking-[0.12em] text-ink-3 uppercase">
        {label}
      </p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="font-display tnum text-2xl font-semibold text-ink">{value}</span>
        <span className="text-xs text-ink-3">{hint}</span>
      </p>
    </div>
  );
}

function ProjectRow({
  project,
  onChanged,
  onRemoved,
}: {
  project: Project;
  onChanged: (project: Project) => void;
  onRemoved: (id: string) => void;
}) {
  const [busy, setBusy] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const canManage = project.role === "owner" || project.role === "admin";
  const canDelete = project.role === "owner";

  async function run(action: () => Promise<Project | void>, remove = false) {
    setBusy(true);
    setActionError(null);
    try {
      const result = await action();
      if (remove) onRemoved(project.id);
      else if (result) onChanged(result as Project);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "The action failed.");
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  const stack = project.runtime_profile;
  return (
    <li>
      <Card interactive>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <Link
            href={`/app/projects/${project.id}`}
            className="group flex min-w-0 flex-1 items-center gap-4 rounded-lg outline-none"
            aria-label={`Open ${project.name}`}
          >
            <span
              aria-hidden="true"
              className="font-display flex size-10 shrink-0 items-center justify-center rounded-xl bg-sage-subtle text-[17px] font-semibold text-sage"
            >
              {project.name.trim().charAt(0).toUpperCase() || "?"}
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="truncate font-medium text-ink group-hover:text-sage">
                  {project.name}
                </span>
                <Badge tone={statusTone(project.status)} dot={false}>
                  {project.status}
                </Badge>
                <Badge tone="neutral" dot={false}>
                  {project.role}
                </Badge>
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {(stack.frameworks ?? []).slice(0, 3).map((framework) => (
                  <span
                    key={framework}
                    className="rounded-md border border-line/70 bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-2"
                  >
                    {framework}
                  </span>
                ))}
                {stack.package_manager && (
                  <span className="rounded-md border border-line/70 bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
                    {stack.package_manager}
                  </span>
                )}
                {project.latest_snapshot?.short_hash && (
                  <span className="font-mono text-[11px] text-ink-3">
                    {project.latest_snapshot.short_hash} · {project.snapshot_count}{" "}
                    {project.snapshot_count === 1 ? "snapshot" : "snapshots"}
                  </span>
                )}
                {!project.latest_snapshot && (
                  <span className="font-mono text-[11px] text-warning">no snapshot yet</span>
                )}
              </span>
              <span className="truncate font-mono text-xs text-ink-3">
                {project.slug} · updated {formatTimestamp(project.updated_at)}
              </span>
            </span>
            <ArrowRight
              aria-hidden="true"
              className="size-4 shrink-0 text-ink-3 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-sage"
            />
          </Link>
          <span className="flex shrink-0 items-center gap-2 pl-14 sm:pl-0">
            <span
              title="Investigations arrive in M4"
              className="inline-flex h-8 cursor-not-allowed items-center rounded-md border border-line/60 px-2.5 text-[13px] font-medium text-ink-3 opacity-60"
              aria-disabled="true"
            >
              New investigation
            </span>
            <Dropdown
              label={`Actions for ${project.name}`}
              trigger={
                <span className="inline-flex h-8 items-center rounded-md border border-line bg-surface-1 px-2.5 text-[13px] font-semibold text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink">
                  Actions
                </span>
              }
            >
              <DropdownLabel>Project</DropdownLabel>
              <DropdownLink href={`/app/projects/${project.id}`}>
                <FolderKanban aria-hidden="true" className="size-4" /> Open project
              </DropdownLink>
              <DropdownLink href={`/app/projects/${project.id}?tab=settings`}>
                <Settings2 aria-hidden="true" className="size-4" /> Project settings
              </DropdownLink>
              <DropdownSeparator />
              {project.status === "active" && canManage && (
                <DropdownItem onSelect={() => void run(() => archiveProject(project.id))}>
                  <Archive aria-hidden="true" className="size-4" /> Archive project
                </DropdownItem>
              )}
              {project.status === "archived" && canManage && (
                <DropdownItem onSelect={() => void run(() => unarchiveProject(project.id))}>
                  <ArchiveRestore aria-hidden="true" className="size-4" /> Restore project
                </DropdownItem>
              )}
              {canDelete &&
                (confirmDelete ? (
                  <DropdownItem onSelect={() => void run(() => deleteProject(project.id), true)}>
                    <Trash2 aria-hidden="true" className="size-4 text-danger" />
                    <span className="font-semibold text-danger">Confirm delete</span>
                  </DropdownItem>
                ) : (
                  <DropdownItem onSelect={() => setConfirmDelete(true)}>
                    <Trash2 aria-hidden="true" className="size-4" /> Delete project…
                  </DropdownItem>
                ))}
            </Dropdown>
          </span>
        </CardContent>
        {(busy || actionError) && (
          <div className="border-t border-line/60 px-5 py-2.5 sm:px-6" aria-live="polite">
            {busy && <p className="text-[13px] text-ink-3">Working…</p>}
            {actionError && !busy && <p className="text-[13px] font-medium text-danger">{actionError}</p>}
          </div>
        )}
      </Card>
    </li>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [state, setState] = React.useState<LoadState>({ status: "loading" });
  const [summary, setSummary] = React.useState<ProjectsSummary | null>(null);
  const [items, setItems] = React.useState<Project[]>([]);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [statusFilter, setStatusFilter] = React.useState<ProjectStatusFilter | null>(null);
  const [sort, setSort] = React.useState<ProjectSort>("updated");
  const [query, setQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Resolve the workspace: explicit ?workspace= wins, else the first one.
  React.useEffect(() => {
    let cancelled = false;
    async function loadWorkspaces() {
      try {
        const { items: list } = await listWorkspaces(100);
        if (cancelled) return;
        setWorkspaces(list);
        if (workspaceParam) {
          setWorkspaceId(workspaceParam);
        } else if (list.length > 0) {
          setWorkspaceId(list[0].id);
        } else {
          setState({ status: "no-workspace" });
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fprojects");
          return;
        }
        setState({
          status: "error",
          message: err instanceof Error ? err.message : "Could not load workspaces.",
        });
      }
    }
    void loadWorkspaces();
    return () => {
      cancelled = true;
    };
  }, [router, workspaceParam]);

  const load = React.useCallback(
    async (workspace: string, append: boolean, cursor: string | null) => {
      if (!append) setState({ status: "loading" });
      try {
        const [page, header] = await Promise.all([
          listProjects(workspace, {
            limit: 25,
            cursor,
            status: statusFilter,
            q: debouncedQuery || null,
            sort,
          }),
          append ? Promise.resolve(summary) : getProjectsSummary(workspace),
        ]);
        setItems((current) => (append ? [...current, ...page.items] : page.items));
        setNextCursor(page.page.next_cursor);
        if (!append && header) setSummary(header);
        setState({ status: "ready" });
      } catch (err) {
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fprojects");
          return;
        }
        setState({
          status: "error",
          message: err instanceof Error ? err.message : "Could not load projects.",
        });
      }
    },
    [router, statusFilter, debouncedQuery, sort, summary],
  );

  React.useEffect(() => {
    if (workspaceId) void load(workspaceId, false, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, statusFilter, debouncedQuery, sort]);

  function handleWorkspaceChange(id: string) {
    setWorkspaceId(id);
    setSummary(null);
    setNextCursor(null);
    router.replace(`/app/projects?workspace=${id}`);
  }

  if (state.status === "loading" && items.length === 0) {
    return (
      <div className="flex flex-col gap-6" aria-label="Loading projects">
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (state.status === "no-workspace") {
    return (
      <div className="flex max-w-xl flex-col gap-4">
        <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-sage uppercase">
          Projects
        </p>
        <h1 className="font-display text-[32px] leading-9 font-semibold tracking-tight">Projects</h1>
        <Alert tone="info" title="Create a workspace first">
          Projects belong to a workspace. Create one, then add your first codebase.
        </Alert>
        <div>
          <Link href="/app">
            <Button variant="secondary">Back to overview</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex max-w-xl flex-col gap-4">
        <Alert tone="danger" title="Could not load projects">{state.message}</Alert>
        <div>
          <Button variant="secondary" onClick={() => workspaceId && void load(workspaceId, false, null)}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const createHref = workspaceId ? `/app/projects/new?workspace=${workspaceId}` : "/app/projects/new";

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-sage uppercase">
            Projects
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">
            Projects
          </h1>
          <p className="mt-1.5 text-[15px] text-ink-2">Manage codebases and repository snapshots.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {workspaces && workspaces.length > 0 && (
            <label className="flex items-center gap-2 text-[13px] text-ink-3">
              Workspace
              <select
                value={workspaceId ?? ""}
                onChange={(event) => handleWorkspaceChange(event.target.value)}
                className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
              >
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Link href={createHref}>
            <Button>
              <Plus aria-hidden="true" className="size-4" /> Add project
            </Button>
          </Link>
        </div>
      </div>

      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Project metrics">
          <MetricCard label="Total" value={summary.total} hint="projects" />
          <MetricCard label="Active" value={summary.active} hint="in progress" />
          <MetricCard label="Snapshots" value={summary.snapshots_recent_7d} hint="last 7 days" />
          <MetricCard label="Attention" value={summary.needs_attention} hint="need a snapshot" />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative min-w-52 flex-1">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3"
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search projects…"
            aria-label="Search projects"
            className="h-10 w-full rounded-[10px] border border-line bg-surface-1 pr-3 pl-9 text-sm text-ink outline-none transition-all duration-200 placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:bg-inset"
          />
        </div>
        <div role="group" aria-label="Status filter" className="flex items-center gap-1 rounded-full border border-line bg-surface-1 p-1">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              onClick={() => setStatusFilter(filter.key)}
              aria-pressed={statusFilter === filter.key}
              className={cn(
                "cursor-pointer rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors duration-200",
                statusFilter === filter.key ? "bg-ink text-canvas" : "text-ink-3 hover:text-ink",
              )}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-ink-3">
          Sort
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as ProjectSort)}
            className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
          >
            {SORTS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-2">
              <FolderKanban aria-hidden="true" className="size-5 text-sage" />
            </span>
            <div>
              <p className="font-medium">No projects yet</p>
              <p className="mt-1 text-[13px] text-ink-2">
                Add a codebase to start investigating software issues.
              </p>
            </div>
            <Link href={createHref}>
              <Button>Add your first project</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <>
          <ul className="flex flex-col gap-3" aria-label="Projects">
            {items.map((project) => (
              <ProjectRow
                key={project.id}
                project={project}
                onChanged={(updated) =>
                  setItems((current) => current.map((p) => (p.id === updated.id ? updated : p)))
                }
                onRemoved={(id) => {
                  setItems((current) => current.filter((p) => p.id !== id));
                  setSummary((current) => (current ? { ...current, total: current.total - 1 } : current));
                }}
              />
            ))}
          </ul>
          {nextCursor && (
            <div>
              <Button
                variant="secondary"
                loading={loadingMore}
                onClick={async () => {
                  if (!workspaceId) return;
                  setLoadingMore(true);
                  try {
                    const page = await listProjects(workspaceId, {
                      limit: 25,
                      cursor: nextCursor,
                      status: statusFilter,
                      q: debouncedQuery || null,
                      sort,
                    });
                    setItems((current) => [...current, ...page.items]);
                    setNextCursor(page.page.next_cursor);
                  } finally {
                    setLoadingMore(false);
                  }
                }}
              >
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
