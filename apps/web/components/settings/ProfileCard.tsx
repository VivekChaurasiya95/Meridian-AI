"use client";

import * as React from "react";
import { updateMe } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthContext";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

function initialsOf(name: string | null, email: string | null): string {
  const source = (name ?? "").trim() || (email ?? "").trim();
  if (source === "") return "?";
  const parts = source.split(/[\s@._-]+/).filter((part) => part.length > 0);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

/** Profile card (SET-01): identity as the backend reports it, plus rename. */
export function ProfileCard() {
  const { user, refresh } = useAuth();
  const [name, setName] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  if (user === null) return null;
  const draft = name ?? user.display_name ?? "";

  async function onSave(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = draft.trim();
    if (trimmed === "" || trimmed === (user?.display_name ?? "")) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateMe({ display_name: trimmed });
      await refresh();
      setName(null);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update your profile.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>How your name appears across workspaces.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="flex size-11 shrink-0 items-center justify-center rounded-full bg-accent font-display text-[15px] font-semibold text-accent-ink"
          >
            {initialsOf(user.display_name, user.email)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[14px] font-semibold text-ink">
              {user.display_name ?? "Unnamed"}
            </p>
            <p className="truncate font-mono text-xs text-ink-3">{user.email ?? "no email"}</p>
          </div>
        </div>
        <form onSubmit={onSave} className="mt-4 flex flex-col gap-3">
          {error !== null && (
            <Alert tone="danger" title="Could not save">
              {error}
            </Alert>
          )}
          {saved && (
            <Alert tone="success" title="Saved">
              Your display name was updated.
            </Alert>
          )}
          <Input
            label="Display name"
            value={draft}
            onChange={(event) => setName(event.target.value)}
            maxLength={100}
          />
          <div>
            <Button
              type="submit"
              size="sm"
              variant="secondary"
              disabled={saving || draft.trim() === "" || draft.trim() === (user.display_name ?? "")}
            >
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
