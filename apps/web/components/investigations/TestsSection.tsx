"use client";

import * as React from "react";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { createRegressionTest, listRegressionTests } from "@/lib/api";
import type { RegressionTest } from "@/lib/types";
import { useToast } from "@/components/ui/Toast";

const STATUS_TONE: Record<string, "success" | "info" | "warning" | "danger" | "neutral"> = {
  proposed: "neutral",
  created: "info",
  baseline_passed: "success",
  baseline_failed: "warning",
  post_patch_passed: "success",
  post_patch_failed: "danger",
  blocked: "warning",
  not_run: "neutral",
};

const TEST_TYPES = ["e2e", "unit", "integration", "regression", "manual"];

/** Regression tests: worker-driven checks plus manual test ideas (M8). */
export function TestsSection({
  investigationId,
  canPropose,
}: {
  investigationId: string;
  /** False on terminal investigations: the API 409s new tests, so offer none. */
  canPropose: boolean;
}) {
  const toast = useToast();
  const [tests, setTests] = React.useState<RegressionTest[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [testType, setTestType] = React.useState("manual");
  const [filePath, setFilePath] = React.useState("");
  const [testName, setTestName] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      setTests(await listRegressionTests(investigationId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load regression tests.");
    }
  }, [investigationId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setActionError(null);
    try {
      await createRegressionTest(investigationId, {
        title: title.trim(),
        description: description.trim() === "" ? undefined : description.trim(),
        test_type: testType,
        file_path: filePath.trim() === "" ? undefined : filePath.trim(),
        test_name: testName.trim() === "" ? undefined : testName.trim(),
      });
      setTitle("");
      setDescription("");
      setFilePath("");
      setTestName("");
      setFormOpen(false);
      toast.success("Test idea proposed.");
      void load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not propose a test.");
    } finally {
      setCreating(false);
    }
  }

  if (error !== null && tests === null) {
    return (
      <section aria-label="Regression tests">
        <h2 className="mb-2 text-[15px] font-semibold">Regression tests</h2>
        <Alert tone="danger" title="Tests unavailable">
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

  if (tests === null) {
    return (
      <section aria-label="Regression tests">
        <h2 className="mb-2 text-[15px] font-semibold">Regression tests</h2>
        <Skeleton className="h-24" />
      </section>
    );
  }

  return (
    <section aria-label="Regression tests">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold">
          Regression tests {tests.length > 0 && `(${tests.length})`}
        </h2>
        {canPropose && (
          <span className="ml-auto">
            <Button size="sm" variant="secondary" onClick={() => setFormOpen((open) => !open)}>
              {formOpen ? "Close" : "Propose test"}
            </Button>
          </span>
        )}
      </div>

      {actionError !== null && (
        <div className="mb-2">
          <Alert tone="danger" title="Action failed">
            {actionError}
          </Alert>
        </div>
      )}

      {formOpen && canPropose && (
        <Card className="mb-2 flex flex-col gap-3 p-4">
          <h3 className="text-[14px] font-semibold">Propose a test idea</h3>
          <p className="text-[13px] text-ink-2">
            Manual ideas record intent. Only worker-created e2e tests with executable steps run
            in verification.
          </p>
          <form onSubmit={onCreate} className="flex flex-col gap-3">
            <Input
              label="Title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="What should this test check?"
              maxLength={200}
            />
            <Input
              label="Description (optional)"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Why does it matter?"
              maxLength={2000}
            />
            <div className="flex flex-col gap-1.5">
              <label htmlFor="test-type" className="text-[13px] font-semibold text-ink">
                Type
              </label>
              <select
                id="test-type"
                value={testType}
                onChange={(event) => setTestType(event.target.value)}
                className="h-10 w-full rounded-[10px] border border-line bg-surface-1 px-3.5 text-[14px] text-ink outline-none focus:border-accent"
              >
                {TEST_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="File path (optional)"
              value={filePath}
              onChange={(event) => setFilePath(event.target.value)}
              placeholder="tests/header.spec"
              maxLength={500}
            />
            <Input
              label="Test name (optional)"
              value={testName}
              onChange={(event) => setTestName(event.target.value)}
              placeholder="header shows the logged-out state"
              maxLength={300}
            />
            <div>
              <Button type="submit" size="sm" disabled={creating || title.trim() === ""}>
                {creating ? "Proposing…" : "Propose"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {tests.length === 0 ? (
        <p className="text-[13px] text-ink-3">
          {canPropose
            ? "No tests yet — the pipeline proposes e2e checks after review, or propose one above."
            : "No tests were proposed before this investigation ended."}
        </p>
      ) : (
        <ol className="flex flex-col gap-2">
          {tests.map((test) => (
            <li key={test.id}>
              <Card className="flex flex-col gap-1.5 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={STATUS_TONE[test.status] ?? "neutral"} dot={false}>
                    {test.status.replace(/_/g, " ")}
                  </Badge>
                  <span className="text-[14px] font-semibold">{test.title}</span>
                  <span className="ml-auto font-mono text-[11px] text-ink-3">
                    {test.test_type}
                    {test.file_path !== null && ` · ${test.file_path}`}
                  </span>
                </div>
                {test.description !== null && (
                  <p className="text-[13px] text-ink-2">{test.description}</p>
                )}
                {test.verification_history.length > 0 && (
                  <p className="font-mono text-[11px] text-ink-3">
                    {test.verification_history
                      .map((entry) => `${entry.phase.replace("_", " ")}: ${entry.check_status}`)
                      .join(" · ")}
                  </p>
                )}
              </Card>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
