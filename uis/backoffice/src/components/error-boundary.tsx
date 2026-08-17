"use client";

import { Component, ReactNode } from "react";

import { hashStack, parseBrowserInfo, track, truncateSafe } from "@/services/telemetry";

type ErrorBoundaryProps = { children: ReactNode };
type ErrorBoundaryState = { hasError: boolean };

/** Wraps the app tree in the root layout; catches render errors React would otherwise crash on. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: { componentStack?: string | null }): void {
    const stack = error.stack ?? `${error.name}: ${error.message}`;
    const componentName = errorInfo.componentStack?.trim().split("\n")[0]?.trim();

    track("frontend_error_captured", {
      error_name: truncateSafe(error.name, 128),
      error_message_safe: truncateSafe(error.message, 256),
      stack_hash: hashStack(stack),
      ...(componentName ? { component: truncateSafe(componentName, 128) } : {}),
      route: typeof window !== "undefined" ? window.location.pathname : "",
      severity: "high",
      handled: false,
      ...parseBrowserInfo(),
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="auth-guard-loading">
          <p>Ha ocurrido un error inesperado. Recarga la pagina para continuar.</p>
        </div>
      );
    }
    return this.props.children;
  }
}
