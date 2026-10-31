"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FolderOpen } from "lucide-react";
import { MeridianApiError, listWorkspaces } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { CreateWorkspaceForm } from "@/components/workspaces/CreateWorkspaceForm";
import { WorkspaceList } from "@/components/workspaces/WorkspaceList";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: Workspace[]; nextCursor: string | null };

export default function OverviewPage() {
  const router = useRouter();
  const [state, setState] = React.useState<LoadState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = React.useState(false);

  const load = React.useCallback(async () => {
    setState({ status: "loading" });
    try {
      const { items, page } = await listWorkspaces();
      setState({ status: "ready", items, nextCursor: page.next_cursor });
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 401) {
        router.push("/login?next=%2Fapp");
        return;
      }
      setState({
        status: "error",
        message: err instanceof Error ? err.message : "Could not load workspaces.",
      });
    }
  }, [router]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (state.status !== "ready" || !state.nextCursor) return;
    setLoadingMore(true);
    try {
      const { items, page } = await listWorkspaces(25, state.nextCursor);
      setState({ status: "ready", items: [...state.items, ...items], nextCursor: page.next_cursor });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof Error ? err.message : "Could not load more workspaces.",
      });
    } finally {
      setLoadingMore(false);
    }
  }

  function handleCreated(workspace: Workspace) {
    setState((current) =>
      current.status === "ready"
        ? { ...current, items: [workspace, ...current.items] }
        : current,
    );
  }

  const count = state.status === "ready" ? state.items.length : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] font-medium tracking-[0.14em] text-sage uppercase">
            Workspace
          </p>
          <h1 className="font-display mt-1.5 text-[32px] leading-9 font-semibold tracking-tight">Overview</h1>
          <p className="mt-1.5 text-[15px] text-ink-2">
            Workspaces managed by this Meridian deployment — loaded live from the API.
          </p>
        </div>
        {count !== null && (
          <p className="rounded-xl border border-line/70 bg-surface-1 px-4 py-2.5 shadow-card">
            <span className="font-display text-xl font-semibold">{count}</span>{" "}
            <span className="text-[13px] text-ink-3">{count === 1 ? "workspace" : "workspaces"}</span>
          </p>
        )}
      </div>

      {state.status === "loading" && (
        <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <div className="flex flex-col gap-3" aria-label="Loading workspaces">
            <Skeleton className="h-[76px]" />
            <Skeleton className="h-[76px]" />
          </div>
          <Skeleton className="h-72" />
        </div>
      )}

      {state.status === "error" && (
        <Alert
          tone="danger"
          title={state.message.includes("unreachable") ? "The API is unreachable" : "Could not load workspaces"}
        >
          <p>{state.message}</p>
          <p className="mt-1 font-mono text-xs">
            Start it with: uvicorn app.main:app --app-dir services/api --port 8010
          </p>
          <div className="mt-3">
            <Button variant="secondary" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        </Alert>
      )}

      {state.status === "ready" && (
        <div className="grid items-start gap-6 lg:grid-cols-[1.6fr_1fr]">
          <section aria-label="Workspaces" className="flex min-w-0 flex-col gap-4">
            {state.items.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                  <span className="flex size-12 items-center justify-center rounded-2xl border border-line bg-surface-2">
                    <FolderOpen aria-hidden="true" className="size-5 text-sage" />
                  </span>
                  <div>
                    <p className="font-medium">No workspaces yet</p>
                    <p className="mt-1 text-[13px] text-ink-2">
                      Create your first workspace to hold projects and investigations.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <>
                <WorkspaceList items={state.items} />
                {state.nextCursor && (
                  <div>
                    <Button variant="secondary" onClick={() => void loadMore()} loading={loadingMore}>
                      Load more
                    </Button>
                  </div>
                )}
              </>
            )}
          </section>
          <CreateWorkspaceForm onCreated={handleCreated} />
        </div>
      )}
    </div>
  );
}
