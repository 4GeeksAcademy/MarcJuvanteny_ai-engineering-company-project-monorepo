"use client";

import { useEffect } from "react";

import { hashStack, parseBrowserInfo, track, truncateSafe } from "@/services/telemetry";
import "./globals.css";

export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    const stack = error.stack ?? `${error.name}: ${error.message}`;
    track("frontend_error_captured", {
      error_name: truncateSafe(error.name, 128),
      error_message_safe: truncateSafe(error.message, 256),
      stack_hash: hashStack(stack),
      route: window.location.pathname,
      severity: "critical",
      handled: false,
      ...parseBrowserInfo(),
    });
  }, [error]);

  return (
    <html lang="es">
      <body className="min-h-full flex flex-col">
        <div className="auth-guard-loading">
          <p>Ha ocurrido un error critico. Recarga la pagina para continuar.</p>
        </div>
      </body>
    </html>
  );
}
