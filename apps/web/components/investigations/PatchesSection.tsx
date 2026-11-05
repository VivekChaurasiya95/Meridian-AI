"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  approvePatch,
  discardPatch,
  formatBytes,
  getPatchDiff,
  listPatches,
  rejectPatch,
} from "@/lib/api";
import type { Patch, PatchDiff, PatchStatus } from "@/lib/types";

const STATUS_TONE: Record<PatchStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  proposed: "neutral",
  awaiting_approval: "warning",
  approved: "info",
  rejected: "danger",
  applied: "info",
  verification_passed: "success",
  verification_failed: "danger",
  stale: "warning",
  discarded: "neutral",
  failed: "danger",
};

const DISCARDABLE: PatchStatus[] = [
  "proposed",
  "awaiting_approval",
  "rejected",
  "failed",
  "verification_failed",
  "stale",
];

function shortDigest(digest: string): string {
  return `${digest.slice(0, 12)}…`;
}

/** Patches: proposals, diff review, and scoped human approval (M8). */
export function PatchesSection({
  investigationId,
  onChanged,
}: {
  investigationId: string;
  onChanged?: () => void;
}) {
  const [patches, setPatches] = React.useState<Patch[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [diffs, setDiffs] = React.useState<Record<string, PatchDiff>>({});
  const [deciding, setDeciding] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");
  const [reason, setReason] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      setPatches(await listPatches(investigationId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load patches.");
    }
  }, [investigationId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function refresh() {
    await load();
    onChanged?.();
  }

  async function onToggleDiff(patch: Patch) {
    if (expanded === patch.id) {
      setExpanded(null);
      return;
    }
    setExpanded(patch.id);
    if (diffs[patch.id] !== undefined) return;
    setActionError(null);
    try {
      const diff = await getPatchDiff(patch.id);
      setDiffs((current) => ({ ...current, [patch.id]: diff }));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not load the diff.");
    }
  }

  async function onApprove(patch: Patch) {
    setWorking(patch.id);
    setActionError(null);
    try {
      // Re-send the exact reviewed binding: the server refuses mismatches.
      await approvePatch(patch.id, {
        diff_sha256: patch.diff_sha256,
        base_snapshot_id: patch.base_snapshot_id,
        note: note.trim() === "" ? undefined : note.trim(),
      });
      setDeciding(null);
      setNote("");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not approve.");
    } finally {
      setWorking(null);
    }
  }

  async function onReject(patch: Patch) {
    setWorking(patch.id);
    setActionError(null);
    try {
      await rejectPatch(patch.id, { reason: reason.trim() });
      setDeciding(null);
      setReason("");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not reject.");
    } finally {
      setWorking(null);
    }
  }

  async function onDiscard(patch: Patch) {
    setWorking(patch.id);
    setActionError(null);
    try {
      await discardPatch(patch.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not discard.");
    } finally {
      setWorking(null);
    }
  }

  if (error !== null && patches === null) {
    return (
      <section aria-label="Patches">
        <h2 className="mb-2 text-[15px] font-semibold">Patches</h2>
        <Alert tone="danger" title="Patches unavailable">
          {error}
        </Alert>
        <div className="mt-2">
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  if (patches === null) {
    return (
      <section aria-label="Patches">
        <h2 className="mb-2 text-[15px] font-semibold">Patches</h2>
        <Skeleton className="h-24" />
      </section>
    );
  }

  return (
    <section aria-label="Patches">
      <h2 className="mb-2 text-[15px] font-semibold">
        Patches {patches.length > 0 && `(${patches.length})`}
      </h2>

      {actionError !== null && (
        <div className="mb-2">
          <Alert tone="danger" title="Action failed">
            {actionError}
          </Alert>
        </div>
      )}

      {patches.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          No patches proposed yet — the pipeline proposes one after baseline verification.
        </p>
      ) : (
        <ol className="flex flex-col gap-2">
          {patches.map((patch) => {
            const diff = diffs[patch.id];
            const busy = working === patch.id;
            const awaiting = patch.status === "awaiting_approval";
            const reviewable = patch.status === "proposed" || awaiting;
            return (
              <li key={patch.id}>
                <Card className="flex flex-col gap-2 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONE[patch.status]} dot={false}>
                      {patch.status.replace(/_/g, " ")}
                    </Badge>
                    <span className="text-[14px] font-semibold">{patch.summary}</span>
                    <span className="ml-auto font-mono text-[11px] text-ink-3">
                      {shortDigest(patch.diff_sha256)} · {formatBytes(patch.diff_byte_size)}
                    </span>
                  </div>
                  <p className="font-mono text-[11px] text-ink-3">
                    {patch.files_changed.length} file(s):{" "}
                    {patch.files_changed
                      .map((file) => `${file.change} ${file.path} (+${file.additions}/-${file.deletions})`)
                      .join(" · ")}
                  </p>
                  {patch.verification !== null && (
                    <p className="text-[13px] text-ink-2">
                      Verification {patch.verification.status.replace("_", " ")}
                      {patch.verification.summary !== null && ` — ${patch.verification.summary}`}
                    </p>
                  )}
                  {patch.approval_note !== null && (
                    <p className="text-[13px] text-ink-2">
                      Reviewer note: {patch.approval_note}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void onToggleDiff(patch)}
                    >
                      {expanded === patch.id ? "Hide diff" : "View diff"}
                    </Button>
                    {awaiting && deciding !== patch.id && (
                      <Button size="sm" onClick={() => setDeciding(patch.id)} disabled={busy}>
                        Review
                      </Button>
                    )}
                    {DISCARDABLE.includes(patch.status) && !awaiting && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => void onDiscard(patch)}
                        disabled={busy}
                      >
                        {busy ? "Working…" : "Discard"}
                      </Button>
                    )}
                  </div>
                  {expanded === patch.id && (
                    <div className="rounded-[10px] border border-line bg-inset p-3">
                      {diff === undefined ? (
                        <Skeleton className="h-20" />
                      ) : "diff_text" in diff ? (
                        <pre className="max-h-80 overflow-auto font-mono text-[12px] leading-5 whitespace-pre-wrap">
                          {diff.diff_text}
                        </pre>
                      ) : (
                        <div className="flex flex-wrap items-center gap-3">
                          <p className="text-[13px] text-ink-2">
                            This diff is too large to preview inline.
                          </p>
                          <a
                            href={diff.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[13px] font-semibold text-accent"
                          >
                            Download diff
                          </a>
                        </div>
                      )}
                    </div>
                  )}
                  {deciding === patch.id && reviewable && (
                    <div className="flex flex-col gap-3 rounded-[10px] border border-line bg-inset p-3">
                      <p className="font-mono text-[11px] text-ink-3">
                        Approving binds sha {shortDigest(patch.diff_sha256)} on snapshot{" "}
                        {patch.base_snapshot_id.slice(0, 8)}. Application runs isolated after
                        commit — never a push or merge.
                      </p>
                      <Input
                        label="Approval note (optional)"
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        placeholder="Why is this safe to apply?"
                        maxLength={500}
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => void onApprove(patch)} disabled={busy}>
                          {busy ? "Approving…" : "Approve and queue"}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setDeciding(null)}
                          disabled={busy}
                        >
                          Cancel
                        </Button>
                      </div>
                      <Input
                        label="Rejection reason"
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                        placeholder="What is wrong with this patch?"
                        maxLength={500}
                      />
                      <div>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void onReject(patch)}
                          disabled={busy || reason.trim() === ""}
                        >
                          {busy ? "Rejecting…" : "Reject patch"}
                        </Button>
                      </div>
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
