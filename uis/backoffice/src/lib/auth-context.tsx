"use client";

import { ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { extractErrorMessage } from "@/lib/api-errors";
import { API_BASE_URL, clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth";
import { HttpMethod, identify, resetSession, timedFetch, track } from "@/services/telemetry";

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
  login: (email: string, password: string, sourceScreen?: string) => Promise<void>;
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
  const loginAttemptCountRef = useRef(0);

  const applyCurrentUser = useCallback((nextUser: AuthUser | null) => {
    if (nextUser) {
      identify(nextUser.email);
      setUser(nextUser);
      setStatus("authenticated");
    } else {
      identify(null);
      clearStoredToken();
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  const loadCurrentUser = useCallback(async (): Promise<AuthUser | null> => {
    const nextUser = await fetchCurrentUser(getStoredToken());
    applyCurrentUser(nextUser);
    return nextUser;
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

    let response: Response;
    try {
      response = await timedFetch(path, () => fetch(`${API_BASE_URL}${path}`, { ...options, headers }), {
        method: (options.method as HttpMethod) || "GET",
        service: "incidents-api",
      });
    } catch {
      throw new Error("No se pudo conectar con el servidor. Verifica tu conexion e intentalo de nuevo.");
    }

    if (response.status === 401) {
      track("session_expired", {
        expired_by: "invalid_token",
        last_route: typeof window !== "undefined" ? window.location.pathname : "",
        http_status: 401,
        reauth_required: true,
      });
      identify(null);
      clearStoredToken();
      setUser(null);
      setStatus("unauthenticated");
    }

    return response;
  }, []);

  const login = useCallback(
    async (email: string, password: string, sourceScreen: string = "login"): Promise<void> => {
      resetSession();
      loginAttemptCountRef.current += 1;
      const attemptNumber = loginAttemptCountRef.current;

      track("auth_login_attempted", {
        auth_method: "password",
        login_channel: "web_backoffice",
        source_screen: sourceScreen,
        attempt_number_in_session: attemptNumber,
      });

      let response: Response;
      try {
        response = await timedFetch(
          "/auth/login",
          () =>
            fetch(`${API_BASE_URL}/auth/login`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email, password }),
            }),
          { method: "POST", service: "incidents-api" }
        );
      } catch {
        track("auth_login_failed", {
          auth_method: "password",
          login_channel: "web_backoffice",
          failure_reason: "api_unavailable",
          source_screen: sourceScreen,
          attempt_number_in_session: attemptNumber,
        });
        throw new Error("No se pudo conectar con el servidor. Verifica tu conexion e intentalo de nuevo.");
      }

      const data = await parseJsonSafely(response);
      if (!response.ok) {
        track("auth_login_failed", {
          auth_method: "password",
          login_channel: "web_backoffice",
          failure_reason: response.status === 401 ? "invalid_credentials" : "api_unavailable",
          http_status: response.status,
          source_screen: sourceScreen,
          attempt_number_in_session: attemptNumber,
        });
        throw new Error(extractErrorMessage(data, "Credenciales invalidas."));
      }

      const tokenPayload = data as { access_token: string; expires_in: number };
      setStoredToken(tokenPayload.access_token);
      const nextUser = await loadCurrentUser();

      if (nextUser) {
        track("auth_login_succeeded", {
          auth_method: "password",
          login_channel: "web_backoffice",
          user_role: nextUser.role,
          token_ttl_seconds: tokenPayload.expires_in,
          source_screen: sourceScreen,
        });
      }
    },
    [loadCurrentUser]
  );

  const logout = useCallback(() => {
    identify(null);
    resetSession();
    clearStoredToken();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    await loadCurrentUser();
  }, [loadCurrentUser]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, logout, refreshUser, authFetch }),
    [user, status, login, logout, refreshUser, authFetch]
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
