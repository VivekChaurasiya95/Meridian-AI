"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MeridianApiError } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthContext";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { SocialAuthButtons } from "@/components/auth/SocialAuthButtons";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";

type SignupFieldErrors = {
  displayName?: string;
  email?: string;
  password?: string;
  confirm?: string;
};

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [displayName, setDisplayName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = React.useState<SignupFieldErrors>({});

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const nextErrors: SignupFieldErrors = {};
    if (confirm !== password) nextErrors.confirm = "Passwords do not match.";
    setFieldErrors(nextErrors);
    if (nextErrors.password || nextErrors.confirm) return;

    setSubmitting(true);
    setError(null);
    try {
      await signup({ email: email.trim(), password, display_name: displayName.trim() });
      router.push("/app");
      router.refresh();
    } catch (err) {
      if (err instanceof MeridianApiError && err.code === "RESOURCE_CONFLICT") {
        setError("An account with this email already exists. Try signing in.");
      } else if (err instanceof MeridianApiError && err.code === "VALIDATION_ERROR") {
        const mapped: SignupFieldErrors = {};
        for (const detail of err.details) {
          if (detail.field === "display_name") mapped.displayName = detail.issue;
          else if (detail.field === "email") mapped.email = detail.issue;
          else if (detail.field === "password") mapped.password = detail.issue;
        }
        setFieldErrors(mapped);
        if (Object.keys(mapped).length === 0) setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Could not create the account.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:text-accent-hover">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <Alert tone="danger" title="Could not create the account">
            {error}
          </Alert>
        )}
        <Input
          label="Display name"
          name="display-name"
          autoComplete="name"
          required
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          error={fieldErrors.displayName}
          placeholder="Ada Lovelace"
          maxLength={100}
        />
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
          placeholder="you@company.com"
        />
        <PasswordInput
          label="Password"
          name="new-password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          hint="Longer is stronger."
          placeholder="Choose a password"
          maxLength={256}
        />
        <PasswordInput
          label="Confirm password"
          name="confirm-password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          error={fieldErrors.confirm}
          placeholder="Repeat the password"
          maxLength={256}
        />
        <Button type="submit" loading={submitting} className="mt-1 w-full">
          Create account
        </Button>
      </form>
      <SocialAuthButtons />
    </AuthLayout>
  );
}
