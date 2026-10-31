"use client";

import * as React from "react";
import { MeridianApiError, createWorkspace } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { Card, CardContent, CardDescription, CardEyebrow, CardHeader, CardTitle } from "@/components/ui/Card";

const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

export function CreateWorkspaceForm({ onCreated }: { onCreated: (workspace: Workspace) => void }) {
  const [name, setName] = React.useState("");
  const [slug, setSlug] = React.useState("");
  const [slugTouched, setSlugTouched] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<{ name?: string; slug?: string }>({});

  function handleNameChange(value: string) {
    setName(value);
    if (!slugTouched) setSlug(suggestSlug(value));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const nextErrors: { name?: string; slug?: string } = {};
    if (!name.trim()) nextErrors.name = "Enter a workspace name.";
    if (!slug) nextErrors.slug = "Enter a slug.";
    else if (!SLUG_PATTERN.test(slug)) nextErrors.slug = "Use lowercase letters, numbers, and hyphens.";
    setFieldErrors(nextErrors);
    if (nextErrors.name || nextErrors.slug) return;

    setSubmitting(true);
    setError(null);
    try {
      const workspace = await createWorkspace({ name: name.trim(), slug });
      onCreated(workspace);
      setName("");
      setSlug("");
      setSlugTouched(false);
      setFieldErrors({});
    } catch (err) {
      if (err instanceof MeridianApiError && err.code === "RESOURCE_CONFLICT") {
        setFieldErrors({ slug: "This slug is taken. Choose another." });
      } else if (err instanceof MeridianApiError && err.code === "VALIDATION_ERROR") {
        const mapped: { name?: string; slug?: string } = {};
        for (const detail of err.details) {
          if (detail.field === "name" || detail.field === "slug") mapped[detail.field] = detail.issue;
        }
        setFieldErrors(mapped);
        if (Object.keys(mapped).length === 0) setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Could not create the workspace.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardEyebrow>New</CardEyebrow>
        <CardTitle>Create workspace</CardTitle>
        <CardDescription>A workspace holds projects and their investigations.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate={false}>
          {error && (
            <Alert tone="danger" title="Could not create the workspace">
              {error}
            </Alert>
          )}
          <Input
            label="Name"
            name="name"
            value={name}
            onChange={(event) => handleNameChange(event.target.value)}
            error={fieldErrors.name}
            placeholder="Product Engineering"
            autoComplete="off"
            maxLength={200}
          />
          <Input
            label="Slug"
            name="slug"
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
              setSlugTouched(true);
            }}
            error={fieldErrors.slug}
            hint="Lowercase letters, numbers, and hyphens. Used in URLs."
            placeholder="product-engineering"
            autoComplete="off"
            maxLength={100}
          />
          <div>
            <Button type="submit" loading={submitting}>
              Create workspace
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
