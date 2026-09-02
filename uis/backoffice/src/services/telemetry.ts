import { API_BASE_URL } from "@/lib/auth";

export const TELEMETRY_SCHEMA_VERSION = "1.0.0";

const TELEMETRY_ENDPOINT = process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT || `${API_BASE_URL}/telemetry/events`;

const MAX_BATCH_SIZE = 20;
const FLUSH_INTERVAL_MS = 10_000;
const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1_000;

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

type TelemetryEvent = {
  eventId: string;
  timestamp: string;
  sessionId: string;
  userId: string;
  event_type: string;
  schemaVersion: string;
  requestId: string;
  properties: Record<string, unknown>;
};

let sessionId: string | null = null;
let currentUserId: string | null = null;
let queue: TelemetryEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function ensureSessionId(): string {
  if (!sessionId) {
    sessionId = crypto.randomUUID();
  }
  return sessionId;
}

/** Called by auth-context on login/logout so subsequent events carry the right userId. */
export function identify(userId: string | null): void {
  currentUserId = userId;
}

/** Starts a fresh session, e.g. on a new login. */
export function resetSession(): void {
  sessionId = crypto.randomUUID();
}

function scheduleFlush(): void {
  if (flushTimer !== null) {
    return;
  }
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flush();
  }, FLUSH_INTERVAL_MS);
}

function cancelScheduledFlush(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}

export function track(eventType: string, properties: Record<string, unknown> = {}): void {
  if (typeof window === "undefined") {
    return;
  }

  const event: TelemetryEvent = {
    eventId: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    sessionId: ensureSessionId(),
    userId: currentUserId ?? "anonymous",
    event_type: eventType,
    schemaVersion: TELEMETRY_SCHEMA_VERSION,
    requestId: crypto.randomUUID(),
    properties,
  };

  queue.push(event);

  if (queue.length >= MAX_BATCH_SIZE) {
    cancelScheduledFlush();
    void flush();
    return;
  }

  scheduleFlush();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function sendBatch(events: TelemetryEvent[]): Promise<void> {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
    try {
      const response = await fetch(TELEMETRY_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events }),
        keepalive: true,
      });
      if (response.ok) {
        return;
      }
    } catch {
      // Network error — fall through to retry.
    }

    if (attempt < MAX_RETRIES) {
      await sleep(RETRY_BASE_DELAY_MS * 2 ** attempt);
    }
  }

  console.warn(`[telemetry] discarded a batch of ${events.length} event(s) after ${MAX_RETRIES} retries.`);
}

async function flush(): Promise<void> {
  if (queue.length === 0) {
    return;
  }
  const batch = queue;
  queue = [];
  await sendBatch(batch);
}

function flushWithBeacon(): void {
  if (queue.length === 0 || typeof navigator === "undefined" || !navigator.sendBeacon) {
    return;
  }
  const batch = queue;
  queue = [];
  const blob = new Blob([JSON.stringify({ events: batch })], { type: "application/json" });
  navigator.sendBeacon(TELEMETRY_ENDPOINT, blob);
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      cancelScheduledFlush();
      flushWithBeacon();
    }
  });
}

function templateEndpoint(path: string): string {
  const withoutQuery = path.split("?")[0];
  return withoutQuery.replace(/\/\d+(?=\/|$)/g, "/:id");
}

function mapFailureReasonFromStatus(status: number): string {
  if (status === 401) {
    return "unauthorized";
  }
  if (status >= 500) {
    return "server_error";
  }
  if (status >= 400) {
    return "validation_error";
  }
  return "server_error";
}

/**
 * Wraps an existing fetch call to emit api_latency_recorded (on any completed
 * response) and api_request_failed (on a non-2xx response or a network error).
 * `path` must be the relative request path (no origin) so it can be templated.
 */
export async function timedFetch(
  path: string,
  fetcher: () => Promise<Response>,
  meta: { method: HttpMethod; service: string }
): Promise<Response> {
  const endpoint = templateEndpoint(path);
  const startedAt = performance.now();

  let response: Response;
  try {
    response = await fetcher();
  } catch (error) {
    track("api_request_failed", {
      endpoint,
      method: meta.method,
      failure_reason: "network_error",
      service: meta.service,
    });
    throw error;
  }

  const latencyMs = Math.round(performance.now() - startedAt);
  track("api_latency_recorded", {
    endpoint,
    method: meta.method,
    status_code: response.status,
    latency_ms: latencyMs,
    service: meta.service,
  });

  if (!response.ok) {
    track("api_request_failed", {
      endpoint,
      method: meta.method,
      status_code: response.status,
      failure_reason: mapFailureReasonFromStatus(response.status),
      service: meta.service,
    });
  }

  return response;
}

/** djb2-style hash, base36-encoded, for a stack fingerprint without storing the raw stack. */
export function hashStack(input: string): string {
  let hash = 5381;
  for (let index = 0; index < input.length; index += 1) {
    hash = (hash * 33) ^ input.charCodeAt(index);
  }
  return `s${(hash >>> 0).toString(36).padStart(7, "0")}`;
}

export function truncateSafe(value: string, maxLength: number): string {
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

export function parseBrowserInfo(): { browser_family?: string; browser_version_major?: number } {
  if (typeof navigator === "undefined") {
    return {};
  }
  const match = navigator.userAgent.match(/(Edg|Chrome|Firefox|Safari)\/(\d+)/);
  if (!match) {
    return {};
  }
  const family = match[1] === "Edg" ? "Edge" : match[1];
  return { browser_family: family, browser_version_major: Number(match[2]) };
}
