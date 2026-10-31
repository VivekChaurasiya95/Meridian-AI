"use client";

import * as React from "react";
import {
  clearSessionFlag,
  getMe,
  hasSessionFlag,
  login as apiLogin,
  loginWithFirebase as apiFirebaseLogin,
  logout as apiLogout,
  signup as apiSignup,
  MeridianApiError,
} from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  login: (input: { email: string; password: string }) => Promise<User>;
  loginWithFirebaseToken: (idToken: string) => Promise<User>;
  signup: (input: { email: string; password: string; display_name: string }) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = React.createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    // No session flag, no probe: anonymous visitors never hit /me (and the
    // API log stays free of benign 401s).
    if (!hasSessionFlag()) {
      setUser(null);
      return;
    }
    try {
      setUser(await getMe());
    } catch (err) {
      if (err instanceof MeridianApiError && err.status === 401) clearSessionFlag();
      setUser(null);
    }
  }, []);

  React.useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const value = React.useMemo<AuthValue>(
    () => ({
      user,
      loading,
      login: async (input) => {
        const next = await apiLogin(input);
        setUser(next);
        return next;
      },
      loginWithFirebaseToken: async (idToken) => {
        const next = await apiFirebaseLogin(idToken);
        setUser(next);
        return next;
      },
      signup: async (input) => {
        const next = await apiSignup(input);
        setUser(next);
        return next;
      },
      logout: async () => {
        try {
          await apiLogout();
        } finally {
          clearSessionFlag();
          setUser(null);
        }
      },
      refresh,
    }),
    [user, loading, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = React.useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
