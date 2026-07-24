"use client";

import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { extractErrorMessage } from "@/lib/api-errors";
import { API_BASE_URL, clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth";

type AuthProfile = {
  name: string | null;
  phone: string | null;
  address: string | null;
};

type AuthUser = {
  email: string;
  role: string;
  profile: AuthProfile | null;
};

type AuthStatus = "checking" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  user: AuthUser | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  authFetch: (path: string, options?: RequestInit) => Promise<Response>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function parseJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchCurrentUser(token: string | null): Promise<AuthUser | null> {
  if (!token) {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as AuthUser;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("checking");

  const applyCurrentUser = useCallback((nextUser: AuthUser | null) => {
    if (nextUser) {
      setUser(nextUser);
      setStatus("authenticated");
    } else {
      clearStoredToken();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  const loadCurrentUser = useCallback(async (): Promise<void> => {
    const nextUser = await fetchCurrentUser(getStoredToken());
    applyCurrentUser(nextUser);
  }, [applyCurrentUser]);

  useEffect(() => {
    void (async () => {
      const nextUser = await fetchCurrentUser(getStoredToken());
      applyCurrentUser(nextUser);
    })();
  }, [applyCurrentUser]);

  const authFetch = useCallback(async (path: string, options: RequestInit = {}): Promise<Response> => {
    const token = getStoredToken();
    const headers = new Headers(options.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

    if (response.status === 401) {
      clearStoredToken();
      setUser(null);
      setStatus("unauthenticated");
    }

    return response;
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await parseJsonSafely(response);
      if (!response.ok) {
        throw new Error(extractErrorMessage(data, "Credenciales invalidas."));
      }

      setStoredToken((data as { access_token: string }).access_token);
      await loadCurrentUser();
    },
    [loadCurrentUser]
  );

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, logout, refreshUser: loadCurrentUser, authFetch }),
    [user, status, login, logout, loadCurrentUser, authFetch]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
