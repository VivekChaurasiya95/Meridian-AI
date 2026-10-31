"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { MeridianApiError } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthContext";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { SocialAuthButtons } from "@/components/auth/SocialAuthButtons";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";

function safeNextPath(value: string | null): string {
  if (value && value.startsWith("/") && !value.startsWith("//")) return value;
  return "/app";
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email: email.trim(), password });
      router.push(safeNextPath(searchParams.get("next")));
      router.refresh();
    } catch (err) {
      if (err instanceof MeridianApiError && err.code === "AUTH_REQUIRED") {
        setError("Invalid email or password.");
      } else if (err instanceof MeridianApiError && err.code === "RATE_LIMITED") {
        setError("Too many attempts. Wait a few minutes and try again.");
      } else {
        setError(err instanceof Error ? err.message : "Could not sign in.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <Alert tone="danger" title="Could not sign in">
          {error}
        </Alert>
      )}
      <Input
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="you@company.com"
      />
      <PasswordInput
        label="Password"
        name="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        placeholder="Your password"
      />
      <Button type="submit" loading={submitting} className="mt-1 w-full">
        Sign in
      </Button>
      </form>
      <SocialAuthButtons redirectTo={safeNextPath(searchParams.get("next"))} />
    </div>
  );
}

export default function LoginPage() {
  return (
    <AuthLayout
      title="Sign in to Meridian"
      subtitle={
        <>
          New here?{" "}
          <Link href="/signup" className="font-medium text-accent hover:text-accent-hover">
            Create an account
          </Link>
        </>
      }
    >
      <React.Suspense>
        <LoginForm />
      </React.Suspense>
    </AuthLayout>
  );
}
