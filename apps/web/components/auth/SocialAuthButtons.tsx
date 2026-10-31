"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { MeridianApiError } from "@/lib/api";
import {
  isFirebaseConfigured,
  signInWithGithub,
  signInWithGoogle,
} from "@/lib/firebase";
import { useAuth } from "@/components/auth/AuthContext";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";

type Provider = "google" | "github";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.4 3.58v2.97h3.88c2.27-2.09 3.57-5.17 3.57-8.74z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-2.97c-1.08.72-2.45 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.28v3.07A12 12 0 0 0 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.29 14.32A7.2 7.2 0 0 1 4.91 12c0-.81.14-1.59.38-2.32V6.61H1.28a12 12 0 0 0 0 10.78l4.01-3.07z"
      />
      <path
        fill="#EA4335"
        d="M12 4.73c1.76 0 3.35.61 4.6 1.8l3.44-3.44A11.98 11.98 0 0 0 12 0 12 12 0 0 0 1.28 6.61l4.01 3.07C6.23 6.84 8.88 4.73 12 4.73z"
      />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px] fill-current" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

function describeError(err: unknown): string {
  if (err instanceof MeridianApiError) {
    if (err.status === 503) {
      return "Social sign-in is not enabled on the server yet.";
    }
    if (err.code === "RATE_LIMITED") {
      return "Too many attempts. Wait a few minutes and try again.";
    }
    return err.message;
  }
  const code =
    typeof err === "object" && err !== null && "code" in err
      ? String((err as { code: unknown }).code)
      : "";
  if (code.includes("popup-closed") || code.includes("cancelled-popup")) {
    return "Sign-in window was closed. Try again.";
  }
  if (code.includes("operation-not-allowed")) {
    return "That provider is not enabled in the Firebase console yet.";
  }
  if (code.includes("unauthorized-domain")) {
    return "This domain is not authorized in the Firebase console yet.";
  }
  if (code.includes("account-exists-with-different-credential")) {
    return "That email already uses a different sign-in method.";
  }
  return err instanceof Error ? err.message : "Could not sign in.";
}

export function SocialAuthButtons({
  redirectTo = "/app",
}: {
  redirectTo?: string;
}) {
  const router = useRouter();
  const { loginWithFirebaseToken } = useAuth();
  const configured = isFirebaseConfigured();
  const [pending, setPending] = React.useState<Provider | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function handle(provider: Provider) {
    setPending(provider);
    setError(null);
    try {
      const idToken =
        provider === "google"
          ? await signInWithGoogle()
          : await signInWithGithub();
      await loginWithFirebaseToken(idToken);
      router.push(redirectTo);
      router.refresh();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-line" />
        <span className="text-xs text-ink-3">or</span>
        <span className="h-px flex-1 bg-line" />
      </div>
      {error && (
        <Alert tone="danger" title="Could not sign in">
          {error}
        </Alert>
      )}
      <div className="flex flex-col gap-3">
        <Button
          type="button"
          variant="secondary"
          className="w-full"
          loading={pending === "google"}
          disabled={!configured || (pending !== null && pending !== "google")}
          onClick={() => void handle("google")}
        >
          <GoogleIcon />
          Continue with Google
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="w-full"
          loading={pending === "github"}
          disabled={!configured || (pending !== null && pending !== "github")}
          onClick={() => void handle("github")}
        >
          <GithubIcon />
          Continue with GitHub
        </Button>
      </div>
      {!configured && (
        <p className="text-xs text-ink-3">
          Social sign-in needs the Firebase keys in{" "}
          <code>apps/web/.env.local</code> first.
        </p>
      )}
    </div>
  );
}
