export const API_BASE_URL = process.env.NEXT_PUBLIC_INCIDENTS_API_URL || "http://localhost:8001";

const TOKEN_STORAGE_KEY = "trackflow_backoffice_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}
