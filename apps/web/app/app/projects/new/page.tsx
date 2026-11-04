"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  Check,
  FileArchive,
  FolderUp,
  GitBranch,
  Loader2,
  X,
} from "lucide-react";
import {
  MeridianApiError,
  createGitImport,
  createProject,
  formatBytes,
  getJob,
  listWorkspaces,
  submitJob,
  uploadProjectArchive,
  validateGitUrl,
} from "@/lib/api";
import type { UploadResult, Workspace } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";

const CLIENT_MAX_BYTES = 25 * 1024 * 1024;
const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

function suggestName(filename: string): string {
  const base = filename.replace(/\.zip$/i, "").replace(/[-_]+/g, " ").trim();
  return base
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
    .slice(0, 200);
}

type Phase =
  | { name: "form" }
  | { name: "creating" }
  | { name: "uploading"; fraction: number }
  | { name: "processing" }
  | { name: "failed"; message: string; projectId: string | null };

const STEPS = ["Source", "Details", "Review"] as const;

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Progress">
      {STEPS.map((label, index) => {
        const done = index < step;
        const current = index === step;
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={cn(
                "flex size-6 items-center justify-center rounded-full text-xs font-bold transition-colors duration-200",
                done || current ? "bg-accent text-accent-ink" : "bg-surface-3 text-ink-3",
              )}
            >
              {done ? <Check className="size-3.5" strokeWidth={3} /> : index + 1}
            </span>
            <span
              className={cn(
                "text-[13px] font-semibold",
                current ? "text-ink" : done ? "text-ink-2" : "text-ink-3",
              )}
              aria-current={current ? "step" : undefined}
            >
              {label}
            </span>
            {index < STEPS.length - 1 && (
              <span aria-hidden="true" className="mx-1 h-px w-6 bg-line-strong sm:w-10" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function NewProjectPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceParam = searchParams.get("workspace");

  const [workspaces, setWorkspaces] = React.useState<Workspace[] | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(workspaceParam);
  const [bootError, setBootError] = React.useState<string | null>(null);
  const [step, setStep] = React.useState(0);
  const [file, setFile] = React.useState<File | null>(null);
  const [fileError, setFileError] = React.useState<string | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [slugTouched, setSlugTouched] = React.useState(false);
  const [description, setDescription] = React.useState("");
  const [fieldErrors, setFieldErrors] = React.useState<{ name?: string; slug?: string }>({});
  const [phase, setPhase] = React.useState<Phase>({ name: "form" });
  const [result, setResult] = React.useState<UploadResult | null>(null);
  const [source, setSource] = React.useState<"zip" | "git">("zip");
  const [gitUrl, setGitUrl] = React.useState("");
  const [gitCanonical, setGitCanonical] = React.useState<string | null>(null);
  const [gitBranches, setGitBranches] = React.useState<{ name: string; commit_sha: string }[]>([]);
  const [gitBranch, setGitBranch] = React.useState("");
  const [gitSha, setGitSha] = React.useState("");
  const [gitBusy, setGitBusy] = React.useState(false);
  const [gitError, setGitError] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function boot() {
      try {
        const { items } = await listWorkspaces(100);
        if (cancelled) return;
        setWorkspaces(items);
        if (workspaceParam) setWorkspaceId(workspaceParam);
        else if (items.length > 0) setWorkspaceId(items[0].id);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MeridianApiError && err.status === 401) {
          router.push("/login?next=%2Fapp%2Fprojects%2Fnew");
          return;
        }
        setBootError(err instanceof Error ? err.message : "Could not load workspaces.");
      }
    }
    void boot();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [router, workspaceParam]);

  function pickFile(next: File | null) {
    setFileError(null);
    if (!next) {
      setFile(null);
      return;
    }
    if (!next.name.toLowerCase().endsWith(".zip")) {
      setFileError("Only .zip archives are accepted.");
      return;
    }
    if (next.size > CLIENT_MAX_BYTES) {
      setFileError(
        `This file is ${formatBytes(next.size)}; the upload limit is ${formatBytes(CLIENT_MAX_BYTES)} (enforced by the server).`,
      );
      return;
    }
    if (next.size === 0) {
      setFileError("The file is empty.");
      return;
    }
    setFile(next);
    if (!name) setName(suggestName(next.name));
    if (!slugTouched) setSlug(suggestSlug(suggestName(next.name)));
  }

  async function handleGitCheck() {
    if (!workspaceId) return;
    setGitBusy(true);
    setGitError(null);
    setGitBranches([]);
    try {
      const valid = await validateGitUrl(gitUrl.trim());
      setGitCanonical(valid.canonical_url);
      if (!name) setName(suggestName(valid.repo));
      if (!slugTouched) setSlug(suggestSlug(valid.repo));
      const job = await submitJob(workspaceId, {
        job_type: "git_preview",
        payload: { repository_url: valid.canonical_url },
      });
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const current = await getJob(job.id);
        if (current.status === "completed") {
          const branches = (current.result?.branches ?? []) as {
            name: string;
            commit_sha: string;
          }[];
          setGitBranches(branches);
          const fallback = (current.result?.default_branch as string | undefined) ?? branches[0]?.name ?? "";
          setGitBranch(fallback);
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          throw new Error(current.error_message ?? "Could not read this repository.");
        }
      }
      throw new Error("Repository check is taking longer than expected. Try again.");
    } catch (err) {
      setGitCanonical(null);
      if (err instanceof MeridianApiError && err.status === 404) {
        setGitError(
          "The API server does not expose POST /api/v1/git/validate (HTTP 404). " +
            "Restart the API on port 8010 from this checkout so the git-import routes load, then try again.",
        );
      } else {
        setGitError(err instanceof Error ? err.message : "Could not check this repository.");
      }
    } finally {
      setGitBusy(false);
    }
  }

  async function handleGitCreate() {
    if (!workspaceId || !gitCanonical) return;
    setPhase({ name: "creating" });
    try {
      const { project } = await createGitImport(workspaceId, {
        name: name.trim(),
        slug,
        description: description.trim() || null,
        repository_url: gitCanonical,
        branch: gitBranch || null,
        commit_sha: gitSha.trim() || null,
      });
      router.push(`/app/projects/${project.id}`);
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 401) {
        router.push("/login?next=%2Fapp%2Fprojects%2Fnew");
        return;
      }
      if (err instanceof MeridianApiError && err.code === "RESOURCE_CONFLICT") {
        setFieldErrors({ slug: "This slug is taken in the selected workspace." });
        setStep(1);
        setPhase({ name: "form" });
        return;
      }
      setPhase({
        name: "failed",
        message: err instanceof Error ? err.message : "Could not create the project.",
        projectId: null,
      });
    }
  }

  function validateDetails(): boolean {
    const errors: { name?: string; slug?: string } = {};
    if (!name.trim()) errors.name = "Enter a project name.";
    if (!slug) errors.slug = "Enter a slug.";
    else if (!SLUG_PATTERN.test(slug)) errors.slug = "Use lowercase letters, numbers, and hyphens.";
    setFieldErrors(errors);
    return !errors.name && !errors.slug;
  }

  async function handleCreate() {
    if (!workspaceId || !file) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase({ name: "creating" });
    setResult(null);
    let projectId: string | null = null;
    try {
      const project = await createProject(workspaceId, {
        name: name.trim(),
        slug,
        description: description.trim() || null,
      });
      projectId = project.id;
      if (controller.signal.aborted) {
        setPhase({ name: "form" });
        return;
      }
      setPhase({ name: "uploading", fraction: 0 });
      const upload = await uploadProjectArchive(
        project.id,
        file,
        (fraction) => {
          if (fraction >= 1) setPhase({ name: "processing" });
          else setPhase({ name: "uploading", fraction });
        },
        controller.signal,
      );
      if (controller.signal.aborted) {
        setPhase({ name: "form" });
        return;
      }
      setResult(upload);
      router.push(`/app/projects/${project.id}`);
    } catch (err) {
      if (controller.signal.aborted) {
        setPhase({ name: "form" });
        return;
      }
      if (err instanceof MeridianApiError && err.status === 401) {
        router.push("/login?next=%2Fapp%2Fprojects%2Fnew");
        return;
      }
      if (err instanceof MeridianApiError && err.code === "RESOURCE_CONFLICT") {
        setFieldErrors({ slug: "This slug is taken in the selected workspace." });
        setStep(1);
        setPhase({ name: "form" });
        return;
      }
      setPhase({
        name: "failed",
        message: err instanceof Error ? err.message : "Could not create the project.",
        projectId,
      });
    }
  }

  if (workspaces === null && !bootError) {
    return (
      <div className="flex max-w-2xl flex-col gap-4" aria-label="Loading">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (bootError || workspaces?.length === 0) {
    return (
      <div className="flex max-w-xl flex-col gap-4">
        <Alert tone={workspaces?.length === 0 ? "info" : "danger"} title="Cannot add a project">
          {bootError ?? "Create a workspace first, then add your first codebase."}
        </Alert>
        <div>
          <Link href="/app">
            <Button variant="secondary">Back to overview</Button>
          </Link>
        </div>
      </div>
    );
  }

  const busy =
    phase.name === "creating" || phase.name === "uploading" || phase.name === "processing";
  const failed = phase.name === "failed" ? phase : null;

  return (
    <div className="flex max-w-2xl animate-fade-in flex-col gap-6">
      <div>
        <Link
          href={workspaceId ? `/app/projects?workspace=${workspaceId}` : "/app/projects"}
          className="group inline-flex items-center gap-1.5 font-mono text-xs font-medium tracking-wide text-ink-3 uppercase transition-colors hover:text-accent"
        >
          Projects
        </Link>
        <h1 className="font-display mt-2 text-[32px] leading-9 font-semibold tracking-tight">
          Add project
        </h1>
        <p className="mt-1.5 text-[15px] text-ink-2">
          Upload a codebase, name it, and review before anything is created.
        </p>
      </div>

      <Stepper step={busy || result ? 2 : step} />

      {failed && (
        <Alert tone="danger" title="Could not create the project">
          <p>{failed.message}</p>
          {failed.projectId && (
            <p className="mt-1">
              The project record was created but the archive failed validation.{" "}
              <Link
                href={`/app/projects/${failed.projectId}`}
                className="font-semibold text-ink underline decoration-sage/50 decoration-2 underline-offset-4 hover:text-sage"
              >
                Open the project
              </Link>{" "}
              to try another archive.
            </p>
          )}
        </Alert>
      )}

      {step === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Source</CardTitle>
            <CardDescription>Where should the code come from?</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div role="group" aria-label="Source type" className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setSource("zip")}
                aria-pressed={source === "zip"}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left",
                  source === "zip"
                    ? "border-sage/40 bg-sage-subtle"
                    : "border-line/70 hover:border-line-strong",
                )}
              >
                <FileArchive aria-hidden="true" className="size-5 shrink-0 text-sage" />
                <span>
                  <span className="block text-sm font-semibold text-ink">Upload ZIP archive</span>
                  <span className="block text-xs text-ink-2">Validated and inspected on upload</span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => setSource("git")}
                aria-pressed={source === "git"}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left",
                  source === "git"
                    ? "border-sage/40 bg-sage-subtle"
                    : "border-line/70 hover:border-line-strong",
                )}
              >
                <GitBranch aria-hidden="true" className="size-5 shrink-0 text-sage" />
                <span>
                  <span className="block text-sm font-semibold text-ink">Git repository</span>
                  <span className="block text-xs text-ink-2">Public GitHub · pinned to a commit</span>
                </span>
              </button>
            </div>

            {source === "git" && (
              <div className="flex flex-col gap-3">
                <Input
                  label="Repository URL"
                  value={gitUrl}
                  onChange={(event) => {
                    setGitUrl(event.target.value);
                    setGitCanonical(null);
                    setGitBranches([]);
                  }}
                  placeholder="https://github.com/owner/repository"
                  autoComplete="off"
                  maxLength={2048}
                />
                {gitCanonical && (
                  <p className="font-mono text-xs text-sage">GitHub · {gitCanonical}</p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={gitBusy}
                    disabled={!gitUrl.trim() || !workspaceId}
                    onClick={() => void handleGitCheck()}
                  >
                    Check repository
                  </Button>
                  {gitBusy && (
                    <span className="text-[13px] text-ink-2">Reading branches from the worker…</span>
                  )}
                </div>
                {gitBranches.length > 0 && (
                  <>
                    <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-ink">
                      Branch
                      <select
                        value={gitBranch}
                        onChange={(event) => setGitBranch(event.target.value)}
                        className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none hover:border-line-strong focus:border-accent"
                      >
                        {gitBranches.map((branch) => (
                          <option key={branch.name} value={branch.name}>
                            {branch.name} · {branch.commit_sha.slice(0, 7)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <Input
                      label="Commit SHA (optional)"
                      value={gitSha}
                      onChange={(event) => setGitSha(event.target.value)}
                      placeholder="Full 40-character SHA to pin exactly"
                      autoComplete="off"
                      maxLength={40}
                    />
                  </>
                )}
                {gitError && (
                  <Alert tone="danger" title="That repository cannot be used">
                    {gitError}
                  </Alert>
                )}
                <p className="rounded-xl border border-line/70 bg-surface-2/60 px-4 py-3 text-[13px] leading-5 text-ink-2">
                  Public GitHub only. The branch is pinned to a commit at import. Code is
                  never executed, and submodules and Git LFS are rejected.
                </p>
                <div className="flex justify-end">
                  <Button disabled={!gitCanonical} onClick={() => setStep(1)}>
                    Continue <ArrowRight aria-hidden="true" className="size-4" />
                  </Button>
                </div>
              </div>
            )}

            {source === "zip" && (
              <>
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragOver(false);
                pickFile(event.dataTransfer.files?.[0] ?? null);
              }}
              className={cn(
                "flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors duration-200",
                dragOver ? "border-sage bg-sage-subtle" : "border-line-strong bg-inset/50",
              )}
            >
              <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-1">
                <FolderUp aria-hidden="true" className="size-5 text-sage" />
              </span>
              <p className="text-sm font-semibold text-ink">
                Drag a .zip here, or{" "}
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="cursor-pointer text-sage underline decoration-sage/50 decoration-2 underline-offset-4 hover:text-ink"
                >
                  browse files
                </button>
              </p>
              <p className="font-mono text-xs text-ink-3">
                .zip only · up to {formatBytes(CLIENT_MAX_BYTES)} · never executed
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".zip,application/zip"
                className="sr-only"
                aria-label="Choose a ZIP archive"
                onChange={(event) => {
                  pickFile(event.target.files?.[0] ?? null);
                  event.target.value = "";
                }}
              />
            </div>
            {fileError && (
              <Alert tone="danger" title="That file cannot be used">
                {fileError}
              </Alert>
            )}
            {file && !fileError && (
              <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-1 px-4 py-3">
                <FileArchive aria-hidden="true" className="size-5 shrink-0 text-sage" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">{file.name}</p>
                  <p className="font-mono text-xs text-ink-3">{formatBytes(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => pickFile(null)}
                  aria-label="Remove file"
                  className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-surface-2 hover:text-danger"
                >
                  <X aria-hidden="true" className="size-4" />
                </button>
              </div>
            )}
            <p className="rounded-xl border border-line/70 bg-surface-2/60 px-4 py-3 text-[13px] leading-5 text-ink-2">
              Repository code is treated as untrusted and is not executed during upload
              validation. Secret files are excluded from indexing.
            </p>
            <div className="flex justify-end">
              <Button disabled={!file || !!fileError} onClick={() => setStep(1)}>
                Continue <ArrowRight aria-hidden="true" className="size-4" />
              </Button>
            </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Project details</CardTitle>
            <CardDescription>Name it like you will find it later.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <label className="flex items-center gap-2 text-[13px] text-ink-3">
              Workspace
              <select
                value={workspaceId ?? ""}
                onChange={(event) => setWorkspaceId(event.target.value)}
                className="h-10 rounded-[10px] border border-line bg-surface-1 px-3 text-[13px] font-semibold text-ink outline-none transition-colors hover:border-line-strong focus:border-accent"
              >
                {workspaces?.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>
                    {workspace.name}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="Name"
              value={name}
              onChange={(event) => {
                const value = event.target.value;
                setName(value);
                if (!slugTouched) setSlug(suggestSlug(value));
              }}
              error={fieldErrors.name}
              placeholder="Billing Service"
              autoComplete="off"
              maxLength={200}
            />
            <Input
              label="Slug"
              value={slug}
              onChange={(event) => {
                setSlug(event.target.value);
                setSlugTouched(true);
              }}
              error={fieldErrors.slug}
              hint="Lowercase letters, numbers, and hyphens. Unique inside the workspace."
              placeholder="billing-service"
              autoComplete="off"
              maxLength={100}
            />
            <div className="flex flex-col gap-1.5">
              <label htmlFor="project-description" className="text-[13px] font-semibold text-ink">
                Description <span className="font-normal text-ink-3">(optional)</span>
              </label>
              <textarea
                id="project-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="What does this codebase do?"
                className="w-full rounded-[10px] border border-line bg-surface-1 px-3.5 py-2.5 text-sm text-ink shadow-[inset_0_1px_2px_rgb(64_45_20/0.06)] transition-all duration-200 outline-none placeholder:text-ink-3 hover:border-line-strong focus:border-accent focus:bg-inset"
              />
            </div>
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep(0)}>
                Back
              </Button>
              <Button
                onClick={() => {
                  if (validateDetails()) setStep(2);
                }}
              >
                Review <ArrowRight aria-hidden="true" className="size-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
            <CardDescription>Nothing is created until you confirm.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <dl className="rounded-xl border border-line/70">
              {(source === "zip"
                ? [
                    ["Project", name.trim()],
                    ["Slug", slug],
                    ["Source", "ZIP archive"],
                    ["Archive", file ? `${file.name} · ${formatBytes(file.size)}` : "—"],
                    ["Workspace", workspaces?.find((w) => w.id === workspaceId)?.name ?? "—"],
                  ]
                : [
                    ["Project", name.trim()],
                    ["Slug", slug],
                    ["Source", "Git repository (GitHub)"],
                    ["Repository", gitCanonical ?? gitUrl],
                    ["Branch", gitBranch || "Default branch"],
                    ["Commit", gitSha.trim() ? gitSha.trim() : "Pinned at import"],
                    ["Workspace", workspaces?.find((w) => w.id === workspaceId)?.name ?? "—"],
                  ]
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="flex items-baseline justify-between gap-6 border-b border-line/60 px-4 py-2.5 last:border-0"
                >
                  <dt className="shrink-0 text-[13px] text-ink-3">{label}</dt>
                  <dd className="truncate text-right font-mono text-[13px]">{value}</dd>
                </div>
              ))}
            </dl>

            {phase.name === "uploading" && (
              <div aria-live="polite">
                <div className="flex items-center justify-between text-[13px] font-medium">
                  <span>Uploading archive…</span>
                  <span className="tnum font-mono text-ink-3">
                    {Math.round(phase.fraction * 100)}%
                  </span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-sage transition-[width] duration-150"
                    style={{ width: `${Math.round(phase.fraction * 100)}%` }}
                  />
                </div>
                <div className="mt-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => abortRef.current?.abort()}
                  >
                    Cancel upload
                  </Button>
                </div>
              </div>
            )}
            {(phase.name === "creating" || phase.name === "processing") && (
              <p className="flex items-center gap-2 text-[13px] text-ink-2" aria-live="polite">
                <Loader2 aria-hidden="true" className="size-4 animate-spin text-sage" />
                {phase.name === "creating"
                  ? "Creating the project…"
                  : "Validating and inspecting the archive…"}
              </p>
            )}

            <div className="flex justify-between">
              <Button variant="secondary" disabled={busy} onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                loading={busy}
                onClick={() => void (source === "git" ? handleGitCreate() : handleCreate())}
              >
                Create project
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
