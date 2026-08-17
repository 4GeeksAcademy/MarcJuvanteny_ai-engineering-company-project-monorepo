"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

import { track } from "@/services/telemetry";

const PUBLIC_ROUTE_PREFIXES = ["/login", "/register", "/forgot-password", "/reset-password"];

function getRouteGroup(pathname: string): string | undefined {
  if (pathname === "/") {
    return "summary";
  }
  if (pathname.startsWith("/inventory")) {
    return "inventory";
  }
  if (pathname.startsWith("/incidents")) {
    return "incidents";
  }
  if (pathname.startsWith("/suppliers")) {
    return "suppliers";
  }
  if (pathname.startsWith("/account")) {
    return "account";
  }
  return undefined;
}

function isProtectedRoute(pathname: string): boolean {
  return !PUBLIC_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

/** Mounted once in the root layout; emits route_changed and page_load_completed on every pathname change. */
export function RouteTracker() {
  const pathname = usePathname();
  const previousPathnameRef = useRef<string | null>(null);
  const navigationStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    const now = performance.now();
    const previousPathname = previousPathnameRef.current;
    const routeGroup = getRouteGroup(pathname);
    const protectedRoute = isProtectedRoute(pathname);

    if (previousPathname !== null && previousPathname !== pathname) {
      track("route_changed", {
        from_route: previousPathname,
        to_route: pathname,
        navigation_source: "programmatic",
        is_protected_route: protectedRoute,
        ...(routeGroup ? { route_group: routeGroup } : {}),
      });
    }

    let loadTimeMs: number;
    if (previousPathname === null) {
      const navigationEntries = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
      loadTimeMs = navigationEntries.length > 0 ? Math.round(navigationEntries[0].loadEventEnd) : 0;
    } else {
      loadTimeMs = Math.round(now - (navigationStartedAtRef.current ?? now));
    }

    const paintEntries = performance.getEntriesByName("first-contentful-paint");

    track("page_load_completed", {
      route: pathname,
      load_time_ms: Math.max(loadTimeMs, 0),
      ...(routeGroup ? { route_group: routeGroup } : {}),
      ...(paintEntries.length > 0 ? { first_contentful_paint_ms: Math.round(paintEntries[0].startTime) } : {}),
    });

    previousPathnameRef.current = pathname;
    navigationStartedAtRef.current = now;
  }, [pathname]);

  return null;
}
