"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import { ChatConnectionState, useCxChat } from "@/lib/use-cx-chat";

const EXAMPLE_QUESTIONS = [
  "¿Dónde está mi pedido?",
  "¿Cuál es la ventana de devolución estándar?",
  "¿Qué transportista cubre mejor Aragón rural?",
];

function connectionLabel(state: ChatConnectionState) {
  if (state.status === "open") return "Conectado";
  if (state.status === "connecting") return "Conectando...";
  if (state.status === "unauthorized") return "Sin sesion -- vuelve a iniciar sesion";
  return `Reconectando en ${Math.ceil(state.retryInMs / 1000)}s (intento ${state.attempt})`;
}

// Hito 10 Parte 2 (CONTEXT10.md): chat con el First-line CX agent por
// WebSocket -- la respuesta se pinta token a token, se puede interrumpir
// (botón "Detener" o escribiendo un mensaje nuevo mientras responde) y la
// conversación se restaura sola al reconectar.
export function KnowledgeQueryPanel() {
  const { messages, connection, isGenerating, notice, send, stop } = useCxChat();
  const [draft, setDraft] = useState("");
  const listEndRef = useRef<HTMLDivElement | null>(null);
  const isOpen = connection.status === "open";

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (send(draft)) setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="card chat-panel">
      <div className="section-header-row">
        <p className="panel-title">Agente de atencion al cliente</p>
        <span className="chat-connection-pill" data-state={connection.status} role="status">
          {connectionLabel(connection)}
        </span>
      </div>

      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 ? (
          <p className="knowledge-status">Escribe una pregunta: seguimiento de pedidos, devoluciones o dudas frecuentes.</p>
        ) : (
          messages.map((message) => (
            <div
              key={message.message_id}
              className={`chat-message chat-message-${message.role}`}
              data-status={message.status}
            >
              <p className="chat-message-text">
                {message.text}
                {message.status === "streaming" ? <span className="chat-caret" aria-hidden="true" /> : null}
              </p>
              {message.status === "interrupted" ? <span className="chat-message-tag">Interrumpida</span> : null}
            </div>
          ))
        )}
        <div ref={listEndRef} />
      </div>

      {notice ? <p className="feedback-error">{notice}</p> : null}

      <form onSubmit={submit} className="chat-composer">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            isGenerating
              ? "Escribe para interrumpir y redirigir la respuesta..."
              : "Ej: ¿cuál es la ventana de devolución estándar?"
          }
          rows={2}
          disabled={!isOpen}
        />
        <div className="chat-composer-actions">
          {isGenerating ? (
            <button type="button" className="secondary-button" onClick={stop} disabled={!isOpen}>
              Detener
            </button>
          ) : null}
          <button type="submit" className="primary-button" disabled={!isOpen || !draft.trim()}>
            {isGenerating ? "Interrumpir y enviar" : "Enviar"}
          </button>
        </div>
      </form>

      <div className="knowledge-examples">
        <span>Ejemplos:</span>
        {EXAMPLE_QUESTIONS.map((example) => (
          <button
            key={example}
            type="button"
            className="knowledge-example-chip"
            onClick={() => setDraft(example)}
            disabled={!isOpen}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
