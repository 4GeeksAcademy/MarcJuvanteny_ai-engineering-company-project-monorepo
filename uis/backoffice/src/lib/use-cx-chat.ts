"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getStoredToken } from "@/lib/auth";
import { KNOWLEDGE_API_URL } from "@/lib/knowledge";

// Hito 10 Parte 2 (CONTEXT10.md): chat con el First-line CX agent por
// WebSocket (`services/knowledge-api/routers/chat.py`). Nombres de campos y
// eventos EXACTOS del BRIEFING: ChatSession { session_id, agent_id, user_id,
// client_id, status, created_at }, eventos token_chunk / interrupt_requested /
// generation_interrupted / generation_completed / session_snapshot /
// user_message.
//
// "Sin perder el hilo": el `session_id` se guarda en localStorage y se
// reenvía en cada reconexión (es también el `thread_id` de LangGraph del
// agente). Al reconectar, el servidor manda primero `session_snapshot` y el
// hook NO acepta ningún `token_chunk` hasta haberlo aplicado; después,
// descarta los tokens cuyo `sequence` ya esté incluido en el snapshot.

export type ChatMessageStatus = "complete" | "streaming" | "interrupted";

export type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  text: string;
  status: ChatMessageStatus;
  sequence: number;
  created_at?: string;
};

export type ChatConnectionState =
  | { status: "connecting" }
  | { status: "open" }
  | { status: "reconnecting"; attempt: number; retryInMs: number }
  | { status: "unauthorized" };

type ServerEvent =
  | { event: "session_snapshot"; data: { session_id: string; status: string; messages: ChatMessage[] } }
  | { event: "user_message"; data: { session_id: string; message_id: string; text: string } }
  | { event: "token_chunk"; data: { session_id: string; message_id: string; token: string; sequence: number } }
  | { event: "generation_interrupted"; data: { session_id: string; message_id: string; status: "interrupted" } }
  | { event: "generation_completed"; data: { session_id: string; message_id: string } }
  | { event: "error"; data: { session_id: string; detail: string } };

const SESSION_STORAGE_KEY = "trackflow_cx_chat_session_id";
const INITIAL_RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

// Códigos de cierre de routers/chat.py.
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_SESSION_GONE = new Set([4403, 4404, 4410]);

function readStoredSessionId(): string | null {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeSessionId(sessionId: string | null) {
  try {
    if (sessionId) window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    else window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Sin storage: la conversación igual funciona, solo no sobrevive a recargar.
  }
}

function websocketUrl(sessionId: string, token: string) {
  const base = KNOWLEDGE_API_URL.replace(/^http/, "ws");
  return `${base}/chat/ws?session_id=${encodeURIComponent(sessionId)}&token=${encodeURIComponent(token)}`;
}

function backoffDelayMs(attempt: number) {
  const exponential = Math.min(MAX_RETRY_MS, INITIAL_RETRY_MS * 2 ** attempt);
  return Math.round(exponential * (0.8 + Math.random() * 0.4));
}

async function createChatSession(token: string): Promise<string> {
  const response = await fetch(`${KNOWLEDGE_API_URL}/chat/sessions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (response.status === 401) throw new Error("unauthorized");
  if (!response.ok) throw new Error("No se pudo crear la sesión de chat.");
  const session = (await response.json()) as { session_id: string };
  return session.session_id;
}

function applyEvent(messages: ChatMessage[], event: ServerEvent): ChatMessage[] {
  switch (event.event) {
    case "session_snapshot":
      return event.data.messages;
    case "user_message":
      if (messages.some((message) => message.message_id === event.data.message_id)) return messages;
      return [
        ...messages,
        { message_id: event.data.message_id, role: "user", text: event.data.text, status: "complete", sequence: -1 },
      ];
    case "token_chunk": {
      const { message_id, token, sequence } = event.data;
      const existing = messages.find((message) => message.message_id === message_id);
      if (!existing) {
        return [...messages, { message_id, role: "assistant", text: token, status: "streaming", sequence }];
      }
      // Ya aplicado (vino incluido en el snapshot): nunca se duplica texto.
      if (sequence <= existing.sequence) return messages;
      return messages.map((message) =>
        message.message_id === message_id ? { ...message, text: message.text + token, sequence } : message
      );
    }
    case "generation_interrupted":
      return messages.map((message) =>
        message.message_id === event.data.message_id ? { ...message, status: "interrupted" } : message
      );
    case "generation_completed":
      return messages.map((message) =>
        message.message_id === event.data.message_id ? { ...message, status: "complete" } : message
      );
    default:
      return messages;
  }
}

export function useCxChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [connection, setConnection] = useState<ChatConnectionState>({ status: "connecting" });
  const [notice, setNotice] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let attempt = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function scheduleReconnect() {
      if (disposed) return;
      const retryInMs = backoffDelayMs(attempt);
      attempt += 1;
      setConnection({ status: "reconnecting", attempt, retryInMs });
      retryTimer = setTimeout(() => void connect(), retryInMs);
    }

    async function connect() {
      if (disposed) return;
      const token = getStoredToken();
      if (!token) {
        setConnection({ status: "unauthorized" });
        return;
      }

      let sessionId = sessionIdRef.current ?? readStoredSessionId();
      if (!sessionId) {
        try {
          sessionId = await createChatSession(token);
        } catch (error) {
          if (error instanceof Error && error.message === "unauthorized") setConnection({ status: "unauthorized" });
          else scheduleReconnect();
          return;
        }
        storeSessionId(sessionId);
      }
      if (disposed) return;
      sessionIdRef.current = sessionId;

      setConnection({ status: "connecting" });
      const socket = new WebSocket(websocketUrl(sessionId, token));
      socketRef.current = socket;
      // Hasta que llegue el snapshot, ningún token se aplica: primero se
      // restaura el contexto, después se aceptan tokens nuevos.
      let hydrated = false;

      socket.onmessage = (raw) => {
        let event: ServerEvent;
        try {
          event = JSON.parse(String(raw.data)) as ServerEvent;
        } catch {
          return;
        }
        if (event.event === "session_snapshot") {
          hydrated = true;
          attempt = 0;
          setConnection({ status: "open" });
        } else if (!hydrated) {
          return;
        }
        if (event.event === "error") {
          setNotice(event.data.detail);
          return;
        }
        setMessages((prev) => applyEvent(prev, event));
      };

      socket.onclose = (closeEvent) => {
        if (socketRef.current === socket) socketRef.current = null;
        if (disposed) return;
        if (closeEvent.code === CLOSE_UNAUTHORIZED) {
          setConnection({ status: "unauthorized" });
          return;
        }
        if (CLOSE_SESSION_GONE.has(closeEvent.code)) {
          // La sesión ya no existe (p. ej. el servicio se reinició: el
          // historial vive en memoria) o está cerrada: se arranca una nueva
          // y se avisa, en vez de reintentar para siempre.
          storeSessionId(null);
          sessionIdRef.current = null;
          setMessages([]);
          setNotice("La conversación anterior ya no está disponible; se inició una nueva.");
          void connect();
          return;
        }
        scheduleReconnect();
      };
    }

    void connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socketRef.current?.close(1000);
    };
  }, []);

  const isGenerating = messages.some((message) => message.status === "streaming");

  const send = useCallback(
    (text: string) => {
      const socket = socketRef.current;
      const sessionId = sessionIdRef.current;
      const trimmed = text.trim();
      if (!socket || socket.readyState !== WebSocket.OPEN || !sessionId || !trimmed) return false;
      setNotice(null);
      // Escribir mientras el agente responde = interrumpir y redirigir.
      socket.send(
        JSON.stringify(
          isGenerating
            ? { event: "interrupt_requested", data: { session_id: sessionId, new_input: trimmed } }
            : { event: "user_message", data: { session_id: sessionId, text: trimmed } }
        )
      );
      return true;
    },
    [isGenerating]
  );

  const stop = useCallback(() => {
    const socket = socketRef.current;
    const sessionId = sessionIdRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !sessionId) return;
    socket.send(JSON.stringify({ event: "interrupt_requested", data: { session_id: sessionId, new_input: null } }));
  }, []);

  return { messages, connection, isGenerating, notice, send, stop };
}
