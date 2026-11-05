"use client";

import * as React from "react";
import { ChevronDown, UserPlus } from "lucide-react";
import {
  MeridianApiError,
  addMember,
  formatTimestamp,
  listMembers,
  removeMember,
  updateMemberRole,
} from "@/lib/api";
import type { AssignableRole, Member } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
};

function RoleSelect({
  value,
  disabled,
  onChange,
  label,
}: {
  value: AssignableRole;
  disabled?: boolean;
  onChange: (role: AssignableRole) => void;
  label: string;
}) {
  return (
    <span className="relative inline-flex items-center">
      <select
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as AssignableRole)}
        className={cn(
          "h-8 appearance-none rounded-[10px] border border-line bg-surface-1 pr-8 pl-2.5 text-[13px] font-medium text-ink transition-colors",
          "hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        <option value="admin">Admin</option>
        <option value="developer">Developer</option>
        <option value="viewer">Viewer</option>
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2 size-3.5 text-ink-3"
      />
    </span>
  );
}

export function MembersCard({
  workspaceId,
  canManage,
  currentUserId,
}: {
  workspaceId: string;
  canManage: boolean;
  currentUserId: string;
}) {
  const toast = useToast();
  const [members, setMembers] = React.useState<Member[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<AssignableRole>("developer");
  const [adding, setAdding] = React.useState(false);
  const [addError, setAddError] = React.useState<string | null>(null);
  const [armedRemove, setArmedRemove] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    try {
      setMembers(await listMembers(workspaceId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load members.");
    }
  }, [workspaceId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      const member = await addMember(workspaceId, { email: email.trim(), role });
      setMembers((current) => (current ? [...current, member] : [member]));
      toast.success(`${member.email ?? "Member"} added as ${member.role}.`);
      setEmail("");
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 404) {
        setAddError("No active account uses this email.");
      } else if (err instanceof MeridianApiError && err.code === "RESOURCE_CONFLICT") {
        setAddError("This user is already a member.");
      } else {
        setAddError(err instanceof Error ? err.message : "Could not add the member.");
      }
    } finally {
      setAdding(false);
    }
  }

  async function handleRoleChange(member: Member, nextRole: AssignableRole) {
    if (nextRole === member.role) return;
    setBusyId(member.user_id);
    try {
      const updated = await updateMemberRole(workspaceId, member.user_id, { role: nextRole });
      setMembers((current) =>
        current ? current.map((m) => (m.user_id === member.user_id ? updated : m)) : current,
      );
      toast.success(`${member.display_name ?? member.email ?? "Member"} is now ${nextRole}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the role.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(member: Member) {
    if (armedRemove !== member.user_id) {
      setArmedRemove(member.user_id);
      return;
    }
    setBusyId(member.user_id);
    try {
      await removeMember(workspaceId, member.user_id);
      setMembers((current) => (current ? current.filter((m) => m.user_id !== member.user_id) : current));
      toast.success(`${member.display_name ?? member.email ?? "Member"} removed.`);
      setArmedRemove(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the member.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>
          {canManage
            ? "Owners and admins can add members and change roles."
            : "Only owners and admins can change membership."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        )}
        {members === null && !error && (
          <div className="flex flex-col gap-2" aria-label="Loading members">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        )}
        {members && (
          <ul className="flex flex-col" aria-label="Workspace members">
            {members.map((member) => {
              const isSelf = member.user_id === currentUserId;
              const isOwner = member.role === "owner";
              const canEditRow = canManage && !isOwner;
              // The server enforces last-owner protection; the UI offers the
              // action and surfaces the refusal honestly.
              const showRemove = canManage || isSelf;
              return (
                <li
                  key={member.user_id}
                  className="flex items-center gap-3 border-b border-line/60 py-2.5 last:border-0"
                >
                  <span
                    aria-hidden="true"
                    className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[13px] font-semibold"
                  >
                    {(member.display_name ?? member.email ?? "?").trim().charAt(0).toUpperCase()}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[13px] font-medium">
                      {member.display_name ?? "Unnamed"}
                      {isSelf && <span className="ml-1.5 text-ink-3">(you)</span>}
                    </span>
                    <span className="truncate font-mono text-xs text-ink-3">
                      {member.email} · joined {formatTimestamp(member.joined_at)}
                    </span>
                  </span>
                  {isOwner ? (
                    <Badge tone="accent">Owner</Badge>
                  ) : canEditRow ? (
                    <RoleSelect
                      label={`Role for ${member.display_name ?? member.email}`}
                      value={member.role as AssignableRole}
                      disabled={busyId === member.user_id}
                      onChange={(next) => void handleRoleChange(member, next)}
                    />
                  ) : (
                    <Badge tone="neutral">{ROLE_LABELS[member.role] ?? member.role}</Badge>
                  )}
                  {showRemove && !isOwner && (
                    <Button
                      variant={armedRemove === member.user_id ? "danger" : "ghost"}
                      size="sm"
                      disabled={busyId === member.user_id}
                      onClick={() => void handleRemove(member)}
                    >
                      {armedRemove === member.user_id ? "Confirm" : "Remove"}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {canManage && (
          <form onSubmit={handleAdd} className="flex flex-col gap-3 border-t border-line pt-4">
            <p className="flex items-center gap-2 text-[13px] font-medium">
              <UserPlus aria-hidden="true" className="size-4 text-ink-3" />
              Add an existing account by email
            </p>
            {addError && (
              <Alert tone="warning" title="Could not add member">
                {addError}
              </Alert>
            )}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1">
                <Input
                  label="Email"
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="teammate@company.com"
                  autoComplete="off"
                />
              </div>
              <div className="flex items-center gap-3">
                <RoleSelect label="Role for new member" value={role} onChange={setRole} />
                <Button type="submit" variant="secondary" loading={adding}>
                  Add
                </Button>
              </div>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
