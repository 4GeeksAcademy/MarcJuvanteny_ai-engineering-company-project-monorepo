"use client";

import { ReactNode, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";
import { track } from "@/services/telemetry";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      track("protected_route_redirected", {
        from_route: pathname,
        to_route: "/login",
        redirect_reason: "unauthenticated",
        guard_name: "AuthGuard",
      });
      router.replace("/login");
    }
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="auth-guard-loading">
        <p>Verificando sesion...</p>
      </div>
    );
  }

  return <>{children}</>;
}
