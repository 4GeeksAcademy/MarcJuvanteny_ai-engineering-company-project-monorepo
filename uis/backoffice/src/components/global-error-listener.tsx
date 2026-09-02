"use client";

import { useEffect } from "react";

import { hashStack, parseBrowserInfo, track, truncateSafe } from "@/services/telemetry";

function reportUncaughtError(error: unknown, severity: "high" | "medium"): void {
  const errorName = error instanceof Error ? error.name : "Error";
  const message = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error && error.stack ? error.stack : `${errorName}: ${message}`;

  track("frontend_error_captured", {
    error_name: truncateSafe(errorName, 128),
    error_message_safe: truncateSafe(message, 256),
    stack_hash: hashStack(stack),
    route: window.location.pathname,
    severity,
    handled: false,
    ...parseBrowserInfo(),
  });
}

/** Mounted once in the root layout; catches errors and promise rejections that no component handled. */
export function GlobalErrorListener() {
  useEffect(() => {
    function handleError(event: ErrorEvent) {
      reportUncaughtError(event.error ?? event.message, "high");
    }

    function handleRejection(event: PromiseRejectionEvent) {
      reportUncaughtError(event.reason, "medium");
    }

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);

    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  return null;
}
