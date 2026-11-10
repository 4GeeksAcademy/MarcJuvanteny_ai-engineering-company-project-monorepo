"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth-context";

// Hito 10 Parte 1 (CONTEXT10.md): consumo del stream SSE `GET /rfp/events`
// con `fetch` + `ReadableStream` -- NO `EventSource`, que no permite mandar
// `Authorization: Bearer ...`. Va por `authFetch`, así que usa el mismo JWT
// del backoffice y un 401 cierra sesión igual que cualquier otra llamada.
//
// Estrategia de recuperación elegida: `Last-Event-ID` + replay en servidor.
// El backend numera cada evento con el id de su outbox en Postgres
// (`rfp_ticket_events.id`) y, al reconectar con `Last-Event-ID: <n>`, reenvía
// todo lo que tenga id > n. El frame de apertura ya trae `id:` (el cursor
// actual), así que incluso una caída antes del primer evento se recupera.
// La UI deduplica por `ticket_id`, nunca por id de evento.

export type RfpTicketCreatedEvent = {
  ticket_id: number;
  rfp_id: number | null;
  client_name: string | null;
  client_country: string | null;
  services_requested: string[];
  status: string;
  created_at: string;
};

export type RfpStreamState =
  | { status: "connecting" }
  | { status: "open" }
  | { status: "reconnecting"; attempt: number; retryInMs: number }
  | { status: "unauthorized" };

type SseFrame = { id?: string; event?: string; data?: string; retry?: number };

const INITIAL_RETRY_MS = 2000;
const MAX_RETRY_MS = 30000;
// El servidor manda `: keep-alive` cada 15s sin eventos -- si pasan 45s sin
// un solo byte, la conexión está muerta aunque el socket no lo haya dicho.
const STALE_STREAM_MS = 45000;

export function parseSseFrame(rawFrame: string): SseFrame {
  const frame: SseFrame = {};
  const dataLines: string[] = [];
  for (const line of rawFrame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "id") frame.id = value;
    else if (field === "event") frame.event = value;
    else if (field === "data") dataLines.push(value);
    else if (field === "retry" && /^\d+$/.test(value)) frame.retry = Number(value);
  }
  if (dataLines.length > 0) frame.data = dataLines.join("\n");
  return frame;
}

export function backoffDelayMs(attempt: number, baseMs: number): number {
  const exponential = Math.min(MAX_RETRY_MS, baseMs * 2 ** attempt);
  // Jitter ±20%: varias pestañas que se caen juntas no reconectan en bloque.
  return Math.round(exponential * (0.8 + Math.random() * 0.4));
}

export function useRfpTicketStream(options: {
  onTicketCreated: (event: RfpTicketCreatedEvent) => void;
  onFirstOpen?: () => void;
}): RfpStreamState {
  const { authFetch } = useAuth();
  const [state, setState] = useState<RfpStreamState>({ status: "connecting" });
  const onTicketCreatedRef = useRef(options.onTicketCreated);
  const onFirstOpenRef = useRef(options.onFirstOpen);

  useEffect(() => {
    onTicketCreatedRef.current = options.onTicketCreated;
    onFirstOpenRef.current = options.onFirstOpen;
  });

  useEffect(() => {
    let disposed = false;
    let lastEventId: string | null = null;
    let baseRetryMs = INITIAL_RETRY_MS;
    let attempt = 0;
    let hasOpenedOnce = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    function scheduleReconnect() {
      if (disposed) return;
      const retryInMs = backoffDelayMs(attempt, baseRetryMs);
      attempt += 1;
      setState({ status: "reconnecting", attempt, retryInMs });
      retryTimer = setTimeout(() => void connect(), retryInMs);
    }

    function handleFrame(frame: SseFrame) {
      if (frame.retry !== undefined) baseRetryMs = frame.retry;
      if (frame.id !== undefined) lastEventId = frame.id;
      if (frame.event !== "rfp_ticket_created" || frame.data === undefined) return;
      try {
        onTicketCreatedRef.current(JSON.parse(frame.data) as RfpTicketCreatedEvent);
      } catch {
        // Un `data:` que no es JSON no debe tumbar el stream entero.
      }
    }

    async function connect() {
      if (disposed) return;
      controller = new AbortController();
      const activeController = controller;
      let staleTimer: ReturnType<typeof setTimeout> | null = null;
      const armStaleTimer = () => {
        if (staleTimer) clearTimeout(staleTimer);
        staleTimer = setTimeout(() => activeController.abort(), STALE_STREAM_MS);
      };

      const headers: Record<string, string> = { Accept: "text/event-stream" };
      if (lastEventId !== null) headers["Last-Event-ID"] = lastEventId;

      try {
        const response = await authFetch("/rfp/events", {
          headers,
          cache: "no-store",
          signal: activeController.signal,
        });

        if (response.status === 401 || response.status === 403) {
          setState({ status: "unauthorized" });
          return;
        }
        if (!response.ok || !response.body) {
          scheduleReconnect();
          return;
        }

        attempt = 0;
        setState({ status: "open" });
        if (!hasOpenedOnce) {
          hasOpenedOnce = true;
          onFirstOpenRef.current?.();
        }

        armStaleTimer();
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          armStaleTimer();
          buffer += value;
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() ?? "";
          for (const rawFrame of frames) handleFrame(parseSseFrame(rawFrame));
        }
      } catch {
        // Red caída, servidor reiniciado o watchdog de keep-alive: todo
        // termina en el mismo reconnect con backoff.
      } finally {
        if (staleTimer) clearTimeout(staleTimer);
      }

      // El stream terminó (o falló) sin que el componente se desmontara.
      scheduleReconnect();
    }

    void connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      controller?.abort();
    };
  }, [authFetch]);

  return state;
}
