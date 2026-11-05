"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  TriangleAlert,
} from "lucide-react";
import {
  MeridianApiError,
  archiveProject,
  createInvestigation,
  deleteProject,
  formatBytes,
  formatTimestamp,
  getFilePreview,
  getJob,
  getProject,
  getSnapshot,
  getTree,
  listInvestigations,
  listSnapshots,
  submitJob,
  unarchiveProject,
  updateProject,
  uploadProjectArchive,
  validateGitUrl,
} from "@/lib/api";
import type {
  FilePreview,
  Investigation,
  InvestigationSeverity,
  InvestigationStatus,
  Project,
  SnapshotDetail,
  SnapshotStorageStatus,
  SnapshotSummary,
  TreeListing,
} from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

type LoadState =
  | { status: "loading" }
  | { status: "not_found" }
  | { status: "error"; message: string }
  | { status: "ready"; project: Project };

const TABS = ["overview", "repository", "snapshots", "investigations", "settings"] as const;
type Tab = (typeof TABS)[number];

function isTab(value: string | null): value is Tab {
  return (TABS as readonly string[]).includes(value ?? "");
}

function MetadataRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-line/60 py-2.5 last:border-0">
      <dt className="shrink-0 text-[13px] text-ink-3">{label}</dt>
      <dd className={cn("min-w-0 truncate text-right text-[13px]", mono && "font-mono")}>{value}</dd>
    </div>
  );
}

const STORAGE_TONE: Record<SnapshotStorageStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  ready: "success",
  uploading: "info",
  pending: "neutral",
  failed: "danger",
  deleting: "warning",
  deleted: "neutral",
  integrity_failed: "danger",
};

const STORAGE_LABEL: Record<SnapshotStorageStatus, string> = {
  ready: "Stored",
  uploading: "Storing",
  pending: "Pending",
  failed: "Storage failed",
  deleting: "Deleting",
  deleted: "Deleted",
  integrity_failed: "Integrity error",
};

function StorageBadge({ status }: { status: SnapshotStorageStatus }) {
  const live = status === "uploading" || status === "deleting";
  return (
    <Badge tone={STORAGE_TONE[status]} pulse={live} dot={true} className="shrink-0">
      {STORAGE_LABEL[status]}
    </Badge>
  );
}

function StackBadges({ project }: { project: Project }) {
  const profile = project.runtime_profile;
  const badges = [
    ...(profile.frameworks ?? []),
    ...(profile.package_manager ? [profile.package_manager] : []),
  ];
  if (badges.length === 0) {
    return <span className="font-mono text-xs text-ink-3">Not detected</span>;
  }
  return (
    <span className="flex flex-wrap gap-1.5">
      {badges.map((badge) => (
        <span
          key={badge}
          className="rounded-md border border-line/70 bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-2"
        >
          {badge}
        </span>
      ))}
    </span>
  );
}

function OverviewTab({ project }: { project: Project }) {
  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Project</CardTitle>
          <CardDescription>Persisted metadata for this project.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl>
            <MetadataRow label="Name" value={project.name} />
            <MetadataRow label="Slug" value={project.slug} mono />
            <MetadataRow label="ID" value={project.id} mono />
            <MetadataRow label="Status" value={project.status} />
            <MetadataRow label="Your role" value={project.role} />
            <MetadataRow label="Snapshots" value={String(project.snapshot_count)} />
            <MetadataRow label="Created" value={formatTimestamp(project.created_at)} />
            <MetadataRow label="Updated" value={formatTimestamp(project.updated_at)} />
          </dl>
          {project.description && (
            <p className="mt-3 border-t border-line/60 pt-3 text-[13px] leading-5 text-ink-2">
              {project.description}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Latest snapshot</CardTitle>
            <CardDescription>The immutable source state investigations use.</CardDescription>
          </CardHeader>
          <CardContent>
            {project.latest_snapshot ? (
              <dl>
                <MetadataRow label="Hash" value={project.latest_snapshot.short_hash ?? "—"} mono />
                <MetadataRow
                  label="Files"
                  value={String(project.latest_snapshot.file_count)}
                  mono
                />
                <MetadataRow label="Archive" value={project.latest_snapshot.archive_name ?? "—"} mono />
                <MetadataRow
                  label="Created"
                  value={formatTimestamp(project.latest_snapshot.created_at)}
                />
              </dl>
            ) : (
              <div className="flex flex-col items-start gap-2">
                <p className="text-sm text-ink-2">
                  No snapshot yet. Upload a ZIP archive to create the first immutable snapshot.
                </p>
                <Badge tone="warning" dot={false}>
                  Needs attention
                </Badge>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Investigations</CardTitle>
            <CardDescription>Bug investigations on this codebase.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-[13px] text-ink-2">
              Investigations arrive in M4. Snapshots created here will pin their source state.
            </p>
            <div className="mt-3">
              <span
                title="Investigations arrive in M4"
                aria-disabled="true"
                className="inline-flex h-9 cursor-not-allowed items-center rounded-[10px] border border-line/60 px-4 text-sm font-medium text-ink-3 opacity-60"
              >
                New investigation
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function RepositoryTab({ project }: { project: Project }) {
  const latestId = project.latest_snapshot?.id ?? null;
  const [tree, setTree] = React.useState<TreeListing | null>(null);
  const [crumbs, setCrumbs] = React.useState<string[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState<FilePreview | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadTree = React.useCallback(
    async (nextCrumbs: string[]) => {
      if (!latestId) return;
      setLoading(true);
      setError(null);
      try {
        const listing = await getTree(latestId, nextCrumbs.join("/"));
        setTree(listing);
        setCrumbs(nextCrumbs);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load the repository tree.");
      } finally {
        setLoading(false);
      }
    },
    [latestId],
  );

  React.useEffect(() => {
    setTree(null);
    setCrumbs([]);
    setSelected(null);
    setPreview(null);
    void loadTree([]);
  }, [loadTree]);

  async function openFile(path: string) {
    if (!latestId) return;
    setSelected(path);
    setPreviewLoading(true);
    try {
      setPreview(await getFilePreview(latestId, path));
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Could not load the file preview.");
    } finally {
      setPreviewLoading(false);
    }
  }

  if (!latestId) {
    return (
      <Alert tone="info" title="No snapshot yet">
        Upload a ZIP archive to browse the repository tree.
      </Alert>
    );
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle>Repository</CardTitle>
          <CardDescription>
            {project.latest_snapshot?.short_hash} · {project.latest_snapshot?.file_count} files
            indexed
          </CardDescription>
        </CardHeader>
        <CardContent>
          <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1 text-[13px]">
            <button
              type="button"
              onClick={() => void loadTree([])}
              className={cn(
                "cursor-pointer rounded-md px-1.5 py-0.5 font-mono transition-colors hover:text-sage",
                crumbs.length === 0 ? "font-semibold text-sage" : "text-ink-3",
              )}
            >
              root
            </button>
            {crumbs.map((crumb, index) => (
              <span key={index} className="flex items-center gap-1">
                <ChevronRight aria-hidden="true" className="size-3.5 text-ink-3" />
                <button
                  type="button"
                  onClick={() => void loadTree(crumbs.slice(0, index + 1))}
                  className={cn(
                    "cursor-pointer rounded-md px-1.5 py-0.5 font-mono transition-colors hover:text-sage",
                    index === crumbs.length - 1 ? "font-semibold text-sage" : "text-ink-3",
                  )}
                >
                  {crumb}
                </button>
              </span>
            ))}
          </nav>
          {loading && <Skeleton className="h-48" />}
          {error && !loading && (
            <Alert tone="danger" title="Could not load the tree">
              {error}
            </Alert>
          )}
          {tree && !loading && (
            <ul className="flex flex-col rounded-xl border border-line/70" aria-label="Files">
              {tree.directories.map((dir) => {
                const name = dir.split("/").pop() ?? dir;
                return (
                  <li key={dir} className="border-b border-line/60 last:border-0">
                    <button
                      type="button"
                      onClick={() => void loadTree(dir.split("/"))}
                      className="flex w-full cursor-pointer items-center gap-2.5 px-3.5 py-2 text-left text-[13px] font-medium text-ink transition-colors hover:bg-surface-2"
                    >
                      <Folder aria-hidden="true" className="size-4 shrink-0 text-sage" />
                      <span className="truncate font-mono">{name}</span>
                      <ChevronRight aria-hidden="true" className="ml-auto size-3.5 text-ink-3" />
                    </button>
                  </li>
                );
              })}
              {tree.entries.map((entry) => {
                const name = entry.path.split("/").pop() ?? entry.path;
                return (
                  <li key={entry.path} className="border-b border-line/60 last:border-0">
                    <button
                      type="button"
                      onClick={() => void openFile(entry.path)}
                      aria-current={selected === entry.path ? "true" : undefined}
                      className={cn(
                        "flex w-full cursor-pointer items-center gap-2.5 px-3.5 py-2 text-left text-[13px] transition-colors hover:bg-surface-2",
                        selected === entry.path ? "bg-sage-subtle" : "text-ink-2",
                      )}
                    >
                      <FileText aria-hidden="true" className="size-4 shrink-0 text-ink-3" />
                      <span className="min-w-0 flex-1 truncate font-mono">{name}</span>
                      <span className="shrink-0 font-mono text-[11px] text-ink-3">
                        {formatBytes(entry.size)}
                      </span>
                    </button>
                  </li>
                );
              })}
              {tree.directories.length === 0 && tree.entries.length === 0 && (
                <li className="px-3.5 py-6 text-center text-[13px] text-ink-3">
                  This directory is empty.
                </li>
              )}
            </ul>
          )}
          {tree && tree.total > tree.entries.length + tree.directories.length && (
            <p className="mt-2 font-mono text-xs text-ink-3">
              Showing {tree.entries.length + tree.directories.length} of {tree.total} items.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>
            {selected ? <span className="font-mono">{selected}</span> : "Select a file to preview"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {previewLoading && <Skeleton className="h-64" />}
          {!previewLoading && preview && (
            <div>
              <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-ink-3">
                <span>{formatBytes(preview.size)}</span>
                <span>sha256 {preview.sha256.slice(0, 12)}…</span>
                {preview.truncated && <span className="text-warning">Preview unavailable</span>}
              </div>
              {preview.content !== null ? (
                <pre className="max-h-[480px] overflow-auto rounded-xl border border-line/70 bg-inset p-4 font-mono text-xs leading-5 whitespace-pre-wrap text-ink-2 break-all">
                  {preview.content}
                </pre>
              ) : (
                <p className="rounded-xl border border-line/70 bg-inset px-4 py-8 text-center text-[13px] text-ink-3">
                  {preview.is_text
                    ? "This file is too large to preview."
                    : "Binary file — no text preview."}
                </p>
              )}
            </div>
          )}
          {!previewLoading && !preview && (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-line/70 bg-inset px-4 py-10 text-center">
              <FolderOpen aria-hidden="true" className="size-5 text-ink-3" />
              <p className="text-[13px] text-ink-3">Text previews render here as plain text.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SnapshotsTab({ project }: { project: Project }) {
  const [items, setItems] = React.useState<SnapshotSummary[]>([]);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<SnapshotDetail | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const page = await listSnapshots(project.id);
        if (cancelled) return;
        setItems(page.items);
        setNextCursor(page.page.next_cursor);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load snapshots.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  async function toggleDetail(id: string) {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setDetailLoading(true);
    try {
      setDetail(await getSnapshot(id));
    } catch (err) {
      setDetail(null);
      setError(err instanceof Error ? err.message : "Could not load the snapshot.");
    } finally {
      setDetailLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-3" aria-label="Loading snapshots">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  if (error && items.length === 0) {
    return <Alert tone="danger" title="Could not load snapshots">{error}</Alert>;
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <p className="font-medium">No snapshots yet</p>
          <p className="max-w-sm text-[13px] text-ink-2">
            Upload a ZIP archive to create the first immutable snapshot of this codebase.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map((snapshot) => {
        const open = expandedId === snapshot.id;
        return (
          <Card key={snapshot.id}>
            <button
              type="button"
              onClick={() => void toggleDetail(snapshot.id)}
              aria-expanded={open}
              className="flex w-full cursor-pointer items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-surface-2/50 sm:px-6"
            >
              <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-sage-subtle font-mono text-[11px] font-bold text-sage"
              >
                {(snapshot.short_hash ?? "?").slice(0, 6)}
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate font-mono text-[13px] font-semibold text-ink">
                  {snapshot.tree_digest}
                </span>
                <span className="truncate font-mono text-xs text-ink-3">
                  {snapshot.archive_name ?? snapshot.source_type} · {snapshot.file_count} files ·{" "}
                  {formatTimestamp(snapshot.created_at)}
                </span>
              </span>
              <StorageBadge status={snapshot.storage_status} />
              <ChevronRight
                aria-hidden="true"
                className={cn(
                  "size-4 shrink-0 text-ink-3 transition-transform duration-200",
                  open && "rotate-90",
                )}
              />
            </button>
            {open && (
              <div className="border-t border-line/70 px-5 py-4 sm:px-6">
                {detailLoading && <Skeleton className="h-40" />}
                {!detailLoading && detail && detail.id === snapshot.id && (
                  <dl>
                    <MetadataRow label="Snapshot ID" value={detail.id} mono />
                    <MetadataRow label="Content hash" value={detail.tree_digest} mono />
                    <MetadataRow label="Archive SHA-256" value={detail.archive_sha256 ?? "—"} mono />
                    <MetadataRow
                      label="Archive size"
                      value={detail.archive_size !== null ? formatBytes(detail.archive_size) : "—"}
                      mono
                    />
                    <MetadataRow label="Storage" value={STORAGE_LABEL[detail.storage_status]} />
                    <MetadataRow
                      label="Stored size"
                      value={detail.storage_bytes !== null ? formatBytes(detail.storage_bytes) : "—"}
                      mono
                    />
                    <MetadataRow
                      label="Verified"
                      value={detail.storage_verified_at ? formatTimestamp(detail.storage_verified_at) : "—"}
                    />
                    {detail.error_code && (
                      <MetadataRow label="Storage error" value={detail.error_message ?? detail.error_code} />
                    )}
                    <MetadataRow
                      label="Languages"
                      value={
                        Object.entries(detail.manifest.languages)
                          .map(([language, count]) => `${language} ${count}`)
                          .join(" · ") || "Not detected"
                      }
                      mono
                    />
                    <MetadataRow
                      label="Frameworks"
                      value={
                        detail.manifest.frameworks.map((f) => f.name).join(", ") || "Not detected"
                      }
                      mono
                    />
                    <MetadataRow label="Package manager" value={detail.manifest.package_manager ?? "Not detected"} mono />
                    <MetadataRow label="Test framework" value={detail.manifest.test_framework ?? "Not detected"} mono />
                    <MetadataRow label="Build system" value={detail.manifest.build_system ?? "Not detected"} mono />
                    <MetadataRow
                      label="Secrets excluded"
                      value={String(detail.manifest.secrets_excluded)}
                      mono
                    />
                  </dl>
                )}
                {!detailLoading && detail && detail.manifest.warnings.length > 0 && (
                  <div className="mt-3 flex flex-col gap-2">
                    {detail.manifest.warnings.map((warning) => (
                      <p key={warning} className="flex items-start gap-2 text-[13px] text-warning">
                        <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                        {warning}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}
      {nextCursor && (
        <div>
          <Button
            variant="secondary"
            loading={loadingMore}
            onClick={async () => {
              setLoadingMore(true);
              try {
                const page = await listSnapshots(project.id, 25, nextCursor);
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
    </div>
  );
}

const INVESTIGATION_TONE: Record<
  InvestigationStatus,
  "success" | "info" | "warning" | "danger" | "neutral"
> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  failed: "danger",
  blocked: "warning",
  inconclusive: "warning",
  cancelled: "neutral",
};

const SEVERITIES: InvestigationSeverity[] = ["low", "medium", "high", "critical", "unspecified"];

function InvestigationsTab({ project }: { project: Project }) {
  const [items, setItems] = React.useState<Investigation[] | null>(null);
  const [snapshots, setSnapshots] = React.useState<SnapshotSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [bugReport, setBugReport] = React.useState("");
  const [severity, setSeverity] = React.useState<InvestigationSeverity>("unspecified");
  const [snapshotId, setSnapshotId] = React.useState("");
  const [route, setRoute] = React.useState("/");

  React.useEffect(() => {
    let live = true;
    listInvestigations(project.id)
      .then((rows) => {
        if (live) setItems(rows);
      })
      .catch((err: unknown) => {
        if (live) setError(err instanceof Error ? err.message : "Could not load investigations.");
      });
    listSnapshots(project.id)
      .then((page) => {
        if (!live) return;
        setSnapshots(page.items);
        const firstReady = page.items.find((item) => item.storage_status === "ready");
        if (firstReady !== undefined) setSnapshotId(firstReady.id);
      })
      .catch(() => {
        if (live) setSnapshots([]);
      });
    return () => {
      live = false;
    };
  }, [project.id]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setFormError(null);
    try {
      const created = await createInvestigation(
        project.id,
        {
          title: title.trim(),
          bug_report: bugReport.trim(),
          severity,
          repository_snapshot_id: snapshotId,
          reproduction_context: { route: route.trim() || "/" },
        },
        `ui-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      );
      setItems((prev) => (prev === null ? [created] : [created, ...prev]));
      setTitle("");
      setBugReport("");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not create the investigation.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-3">
        <h2 className="text-[15px] font-semibold">Open a case</h2>
        {formError !== null && (
          <Alert tone="danger" title="Could not create">
            {formError}
          </Alert>
        )}
        <form onSubmit={onCreate} className="flex flex-col gap-3">
          <Input
            label="Title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="What is broken?"
            maxLength={200}
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="inv-bug-report" className="text-[13px] font-semibold text-ink">
              Bug report
            </label>
            <textarea
              id="inv-bug-report"
              value={bugReport}
              onChange={(event) => setBugReport(event.target.value)}
              placeholder="Steps to reproduce, expected versus actual behavior."
              rows={5}
              maxLength={20000}
              className="w-full rounded-[10px] border border-line bg-surface-1 px-3.5 py-2.5 text-[14px] text-ink shadow-[inset_0_1px_2px_rgb(64_45_20/0.06)] transition-all duration-200 outline-none placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:bg-inset focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_22%,transparent)]"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="inv-severity" className="text-[13px] font-semibold text-ink">
                Severity
              </label>
              <select
                id="inv-severity"
                value={severity}
                onChange={(event) => setSeverity(event.target.value as InvestigationSeverity)}
                className="h-10 w-full rounded-[10px] border border-line bg-surface-1 px-3.5 text-[14px] text-ink outline-none focus:border-accent"
              >
                {SEVERITIES.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="Route"
              value={route}
              onChange={(event) => setRoute(event.target.value)}
              placeholder="/login"
              maxLength={200}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="inv-snapshot" className="text-[13px] font-semibold text-ink">
              Snapshot
            </label>
            <select
              id="inv-snapshot"
              value={snapshotId}
              onChange={(event) => setSnapshotId(event.target.value)}
              className="h-10 w-full rounded-[10px] border border-line bg-surface-1 px-3.5 text-[14px] text-ink outline-none focus:border-accent"
            >
              {(snapshots ?? []).map((snapshot) => (
                <option key={snapshot.id} value={snapshot.id}>
                  {snapshot.archive_name} · {snapshot.storage_status}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Button
              type="submit"
              size="sm"
              disabled={creating || title.trim() === "" || bugReport.trim() === "" || snapshotId === ""}
            >
              {creating ? "Opening…" : "Open investigation"}
            </Button>
          </div>
        </form>
      </div>
      <div className="flex flex-col gap-2">
        <h2 className="text-[15px] font-semibold">Cases</h2>
        {error !== null && (
          <Alert tone="danger" title="Could not load">
            {error}
          </Alert>
        )}
        {items === null ? (
          <Skeleton className="h-24" />
        ) : items.length === 0 ? (
          <p className="text-[13px] text-ink-3">No investigations yet — open the first case.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {items.map((item) => (
              <li key={item.id}>
                <Link href={`/app/investigations/${item.id}`}>
                  <Card className="flex flex-wrap items-center gap-2 p-4 transition-colors hover:border-line-strong">
                    <Badge tone={INVESTIGATION_TONE[item.status]} dot={false}>
                      {item.status.replace("_", " ")}
                    </Badge>
                    <span className="min-w-0 flex-1 truncate text-[14px] font-semibold">
                      {item.title}
                    </span>
                    <span className="font-mono text-xs text-ink-3">
                      {formatTimestamp(item.created_at)}
                    </span>
                  </Card>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function SettingsTab({
  project,
  onChanged,
}: {
  project: Project;
  onChanged: (project: Project) => void;
}) {
  const router = useRouter();
  const [name, setName] = React.useState(project.name);
  const [description, setDescription] = React.useState(project.description ?? "");
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);
  const [working, setWorking] = React.useState(false);
  const [lifecycleError, setLifecycleError] = React.useState<string | null>(null);
  const [confirming, setConfirming] = React.useState<"archive" | "delete" | null>(null);
  const archiveInputRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const [uploadFraction, setUploadFraction] = React.useState<number | null>(null);
  const [uploadError, setUploadError] = React.useState<string | null>(null);
  const [uploadDone, setUploadDone] = React.useState(false);
  const [gitUrl, setGitUrl] = React.useState(project.repository_url ?? "");
  const [gitBranch, setGitBranch] = React.useState(project.default_branch ?? "");
  const [gitBusy, setGitBusy] = React.useState(false);
  const [gitError, setGitError] = React.useState<string | null>(null);
  const [gitDone, setGitDone] = React.useState<string | null>(null);

  const canManage = project.role === "owner" || project.role === "admin";
  const canUpload = project.role !== "viewer";

  async function handleArchiveFile(file: File | null) {
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setUploadError("Only .zip archives are accepted.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    setUploadDone(false);
    setUploadFraction(0);
    try {
      await uploadProjectArchive(project.id, file, setUploadFraction);
      onChanged(await getProject(project.id));
      setUploadDone(true);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "The upload failed.");
    } finally {
      setUploading(false);
      setUploadFraction(null);
    }
  }
  async function handleGitFetch() {
    if (gitBusy || uploading) return;
    const url = gitUrl.trim();
    if (!url) {
      setGitError("Enter a public GitHub repository URL.");
      return;
    }
    setGitBusy(true);
    setGitError(null);
    setGitDone(null);
    try {
      const valid = await validateGitUrl(url);
      const branch = gitBranch.trim();
      const job = await submitJob(project.workspace_id, {
        job_type: "git_import",
        payload: {
          project_id: project.id,
          repository_url: valid.canonical_url,
          ...(branch ? { branch } : {}),
        },
      });
      for (let attempt = 0; attempt < 60; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const current = await getJob(job.id);
        if (current.status === "completed") {
          const sha = current.result?.commit_sha;
          onChanged(await getProject(project.id));
          setGitDone(
            typeof sha === "string" && sha
              ? `Snapshot stored from ${valid.canonical_url} at ${sha.slice(0, 7)}. Open the Snapshots tab to inspect it.`
              : `Snapshot stored from ${valid.canonical_url}. Open the Snapshots tab to inspect it.`,
          );
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          throw new Error(current.error_message ?? "Could not fetch this repository.");
        }
      }
      throw new Error("The import is taking longer than expected. Check the Snapshots tab again shortly.");
    } catch (err) {
      setGitError(err instanceof Error ? err.message : "Could not fetch this repository.");
    } finally {
      setGitBusy(false);
    }
  }
  const canDelete = project.role === "owner";
  const profile = project.runtime_profile;

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setSaveError("Enter a project name.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      onChanged(await updateProject(project.id, { name: name.trim(), description: description.trim() || null }));
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  async function handleLifecycle(action: "archive" | "unarchive" | "delete") {
    setWorking(true);
    setLifecycleError(null);
    try {
      if (action === "archive") onChanged(await archiveProject(project.id));
      else if (action === "unarchive") onChanged(await unarchiveProject(project.id));
      else {
        await deleteProject(project.id);
        router.push(`/app/projects?workspace=${project.workspace_id}`);
        return;
      }
    } catch (err) {
      setLifecycleError(err instanceof Error ? err.message : "The action failed.");
    } finally {
      setWorking(false);
      setConfirming(null);
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>Name and description for this project.</CardDescription>
        </CardHeader>
        <CardContent>
          {canManage ? (
            <form onSubmit={handleSave} className="flex flex-col gap-4">
              {saveError && <Alert tone="danger" title="Could not save">{saveError}</Alert>}
              {saved && (
                <p className="flex items-center gap-1.5 text-[13px] font-medium text-success" role="status">
                  <Check aria-hidden="true" className="size-4" /> Saved.
                </p>
              )}
              <Input
                label="Name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={200}
              />
              <div className="flex flex-col gap-1.5">
                <label htmlFor="settings-description" className="text-[13px] font-semibold text-ink">
                  Description
                </label>
                <textarea
                  id="settings-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                  maxLength={2000}
                  className="w-full rounded-[10px] border border-line bg-surface-1 px-3.5 py-2.5 text-sm text-ink outline-none transition-all duration-200 placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:bg-inset"
                />
              </div>
              <div>
                <Button type="submit" variant="secondary" loading={saving}>
                  Save changes
                </Button>
              </div>
            </form>
          ) : (
            <p className="text-[13px] text-ink-2">
              Your role ({project.role}) cannot change project settings.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Source archive</CardTitle>
          <CardDescription>Upload a ZIP archive or fetch a public GitHub repository to create a new immutable snapshot. Validated, inspected, and stored on arrival.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {uploadError && <Alert tone="danger" title="Upload failed">{uploadError}</Alert>}
          {uploadDone && (
            <p className="flex items-center gap-1.5 text-[13px] font-medium text-success" role="status">
              <Check aria-hidden="true" className="size-4" /> Snapshot stored. Open the Snapshots tab to inspect it.
            </p>
          )}
          {gitError && <Alert tone="danger" title="Fetch failed">{gitError}</Alert>}
          {gitDone && (
            <p className="flex items-center gap-1.5 text-[13px] font-medium text-success" role="status">
              <Check aria-hidden="true" className="size-4" /> {gitDone}
            </p>
          )}
          {canUpload && project.status === "active" ? (
            <>
              <div className="flex flex-wrap items-center gap-2.5">
                <Button
                  variant="secondary"
                  loading={uploading}
                  onClick={() => archiveInputRef.current?.click()}
                >
                  {uploading && uploadFraction !== null
                    ? `Uploading… ${Math.round(uploadFraction * 100)}%`
                    : "Upload ZIP archive"}
                </Button>
                <input
                  ref={archiveInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="sr-only"
                  aria-label="Choose a ZIP archive"
                  onChange={(event) => {
                    void handleArchiveFile(event.target.files?.[0] ?? null);
                    event.target.value = "";
                  }}
                />
              </div>
              <div aria-hidden="true" className="flex items-center gap-3">
                <span className="h-px flex-1 bg-line/70" />
                <span className="font-mono text-[11px] tracking-wide text-ink-3 uppercase">or fetch from GitHub</span>
                <span className="h-px flex-1 bg-line/70" />
              </div>
              <div className="flex flex-col gap-3">
                <Input
                  label="Repository URL"
                  placeholder="https://github.com/owner/repository"
                  value={gitUrl}
                  onChange={(event) => setGitUrl(event.target.value)}
                  maxLength={2048}
                  disabled={gitBusy}
                />
                <Input
                  label="Branch (optional)"
                  placeholder="Defaults to the repository's default branch"
                  value={gitBranch}
                  onChange={(event) => setGitBranch(event.target.value)}
                  maxLength={256}
                  disabled={gitBusy}
                />
                <div>
                  <Button
                    variant="secondary"
                    loading={gitBusy}
                    onClick={() => void handleGitFetch()}
                  >
                    {gitBusy ? "Fetching…" : "Fetch from GitHub"}
                  </Button>
                </div>
                <p className="text-[12px] leading-5 text-ink-3">
                  Public GitHub repositories only. The branch is pinned to its exact commit at import.
                </p>
              </div>
            </>
          ) : (
            <p className="text-[13px] text-ink-2">
              {project.status !== "active"
                ? "Archived projects do not accept new snapshots."
                : `Your role (${project.role}) cannot add snapshots.`}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Runtime</CardTitle>
          <CardDescription>Detected from the latest snapshot. Server-owned.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl>
            <MetadataRow label="Languages" value={(profile.languages ?? []).join(", ") || "Not detected"} mono />
            <MetadataRow label="Frameworks" value={(profile.frameworks ?? []).join(", ") || "Not detected"} mono />
            <MetadataRow label="Package manager" value={profile.package_manager ?? "Not detected"} mono />
            <MetadataRow label="Test framework" value={profile.test_framework ?? "Not detected"} mono />
            <MetadataRow label="Build system" value={profile.build_system ?? "Not detected"} mono />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Lifecycle</CardTitle>
          <CardDescription>Archive pauses new uploads. Delete is permanent.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {lifecycleError && <Alert tone="danger" title="Action failed">{lifecycleError}</Alert>}
          {!canManage && (
            <p className="text-[13px] text-ink-2">
              Your role ({project.role}) cannot change the project lifecycle.
            </p>
          )}
          {canManage && project.status === "active" && (
            <div className="flex flex-wrap items-center gap-2.5">
              {confirming === "archive" ? (
                <>
                  <span className="text-[13px] font-medium">Archive this project?</span>
                  <Button size="sm" loading={working} onClick={() => void handleLifecycle("archive")}>
                    Confirm archive
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setConfirming(null)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="secondary" onClick={() => setConfirming("archive")}>
                  Archive project
                </Button>
              )}
            </div>
          )}
          {canManage && project.status === "archived" && (
            <div className="flex flex-wrap items-center gap-2.5">
              <Button variant="secondary" loading={working} onClick={() => void handleLifecycle("unarchive")}>
                Restore project
              </Button>
            </div>
          )}
          {canDelete && (
            <div className="flex flex-wrap items-center gap-2.5 border-t border-line/60 pt-3">
              {confirming === "delete" ? (
                <>
                  <span className="text-[13px] font-medium text-danger">
                    Delete this project and all its snapshots? This cannot be undone.
                  </span>
                  <Button size="sm" loading={working} onClick={() => void handleLifecycle("delete")}>
                    Confirm delete
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setConfirming(null)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="danger" onClick={() => setConfirming("delete")}>
                  Delete project…
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = isTab(searchParams.get("tab")) ? (searchParams.get("tab") as Tab) : "overview";

  const [state, setState] = React.useState<LoadState>({ status: "loading" });

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const project = await getProject(id);
        if (!cancelled) setState({ status: "ready", project });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push(`/login?next=${encodeURIComponent(`/app/projects/${id}`)}`);
        } else if (err instanceof MeridianApiError && err.status === 404) {
          setState({ status: "not_found" });
        } else {
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Could not load the project.",
          });
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id, router]);

  function setTab(tab: Tab) {
    router.replace(`/app/projects/${id}?tab=${tab}`, { scroll: false });
  }

  if (state.status === "loading") {
    return (
      <div className="flex flex-col gap-6" aria-label="Loading project">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        <Alert tone="warning" title="Project not found">
          It may have been deleted, or the address is wrong.
        </Alert>
        <div>
          <Link
            href="/app/projects"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface-1 px-3 text-[13px] hover:border-line-strong"
          >
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to projects
          </Link>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        <Alert tone="danger" title="Could not load the project">{state.message}</Alert>
        <div>
          <Link
            href="/app/projects"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface-1 px-3 text-[13px] hover:border-line-strong"
          >
            <ArrowLeft aria-hidden="true" className="size-4" /> Back to projects
          </Link>
        </div>
      </div>
    );
  }

  const { project } = state;

  return (
    <div className="flex animate-fade-in flex-col gap-6">
      <div>
        <Link
          href={project.workspace_id ? `/app/projects?workspace=${project.workspace_id}` : "/app/projects"}
          className="group inline-flex items-center gap-1.5 font-mono text-xs font-medium tracking-wide text-ink-3 uppercase transition-colors hover:text-accent"
        >
          <ArrowLeft aria-hidden="true" className="size-3.5 transition-transform duration-200 group-hover:-translate-x-0.5" />{" "}
          Projects
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <span
            aria-hidden="true"
            className="font-display flex size-11 items-center justify-center rounded-xl bg-sage-subtle text-xl font-semibold text-sage"
          >
            {project.name.trim().charAt(0).toUpperCase() || "?"}
          </span>
          <h1 className="font-display text-[32px] leading-9 font-semibold tracking-tight">
            {project.name}
          </h1>
          <Badge tone={project.status === "active" ? "accent" : "neutral"} dot={false}>
            {project.status}
          </Badge>
        </div>
        {project.description && <p className="mt-1.5 text-[15px] text-ink-2">{project.description}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StackBadges project={project} />
          {project.latest_snapshot?.short_hash && (
            <span className="font-mono text-xs text-ink-3">
              snapshot {project.latest_snapshot.short_hash}
            </span>
          )}
          <span className="ml-auto flex items-center gap-2">
            <span
              title="Investigations arrive in M4"
              aria-disabled="true"
              className="inline-flex h-9 cursor-not-allowed items-center rounded-[10px] border border-line/60 px-4 text-sm font-medium text-ink-3 opacity-60"
            >
              New investigation
            </span>
            <Button size="sm" variant="secondary" onClick={() => setTab("settings")}>
              Project settings
            </Button>
          </span>
        </div>
      </div>

      <div role="tablist" aria-label="Project sections" className="flex gap-1 overflow-x-auto border-b border-line/70 no-scrollbar">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setTab(tab)}
            className={cn(
              "relative shrink-0 cursor-pointer px-4 py-2.5 text-[13px] font-semibold capitalize transition-colors duration-200",
              activeTab === tab ? "text-ink" : "text-ink-3 hover:text-ink-2",
            )}
          >
            {tab}
            <span
              aria-hidden="true"
              className={cn(
                "absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-sage transition-all duration-200",
                activeTab === tab ? "opacity-100" : "opacity-0",
              )}
            />
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {activeTab === "overview" && <OverviewTab project={project} />}
        {activeTab === "repository" && <RepositoryTab project={project} />}
        {activeTab === "snapshots" && <SnapshotsTab project={project} />}
        {activeTab === "investigations" && <InvestigationsTab project={project} />}
        {activeTab === "settings" && (
          <SettingsTab
            project={project}
            onChanged={(updated) => setState({ status: "ready", project: updated })}
          />
        )}
      </div>
    </div>
  );
}
