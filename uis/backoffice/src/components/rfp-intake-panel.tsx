"use client";

import { ChangeEvent, DragEvent, useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth-context";
import { RfpStreamState, RfpTicketCreatedEvent, useRfpTicketStream } from "@/lib/use-rfp-ticket-stream";

type TicketStatus =
  | "analizando"
  | "descartado"
  | "analisis_completo"
  | "generando_borrador"
  | "en_evaluación"
  | "needs_human_review"
  | "esperando_aprobación"
  | "terminado"
  | string;

type RfpMetadata = {
  client_name: string | null;
  client_country: string | null;
  services_requested: string[];
  monthly_volume: number | null;
  deadline: string | null;
  budget_range: string | null;
  departments_needed: string[];
};

type DepartmentSection = {
  department_id: string;
  key_aspects: Record<string, unknown>;
  draft_content: string | null;
  evaluation_results: { overall_pass?: boolean } | null;
  approval_status: string | null;
  approver: string | null;
  approved_at: string | null;
};

type FinalDocument = {
  ticket_id: number;
  sections: Record<string, string>;
  currency: string;
  generated_at: string;
};

type TicketDetail = {
  ticket: {
    id: number;
    status: TicketStatus;
    discard_reason: string | null;
    created_at: string;
    updated_at: string;
  };
  metadata: RfpMetadata | null;
  sections: DepartmentSection[];
  final_document: FinalDocument | null;
};

// Hito 9 Parte 3 ("Aprobación humana por departamento"): la Parte 1 pide
// aprobar/rechazar `{ decision, reason }` -- este payload llega del grafo
// (`approval_graph.py::ApprovalState`, no de esta UI), nunca se recalcula
// el `interrupt_id` acá.
type PendingApproval = {
  ticket_id: number;
  department_id: string;
  approver: string;
  draft_content: string;
  evaluation_results: { overall_pass?: boolean } | null;
  iteration: number;
  interrupt_id: string;
};

type ApprovalRoundState = {
  ticket_id: number;
  status: TicketStatus;
  pending_approvals: PendingApproval[];
  final_document?: FinalDocument | null;
};

const STATUS_LABELS: Record<string, string> = {
  analizando: "Analizando...",
  descartado: "Descartado",
  analisis_completo: "Analisis completo",
  generando_borrador: "Generando propuesta...",
  "en_evaluación": "En evaluacion",
  needs_human_review: "Necesita revision humana",
  "esperando_aprobación": "Esperando aprobacion",
  terminado: "Terminado",
};

const DEPARTMENT_LABELS: Record<string, string> = {
  warehouse: "Warehouse Operations",
  lastmile: "Last Mile and Carrier Management",
  reverse: "Reverse Logistics",
};

function statusBadgeClass(status: TicketStatus) {
  if (status === "analisis_completo" || status === "terminado") return "badge-ok";
  if (status === "descartado" || status === "needs_human_review") return "badge-warn";
  return "badge-pending";
}

// Hito 10 Parte 1: el payload de `rfp_ticket_created` ya trae lo necesario
// para pintar el ticket -- se agrega a la lista tal cual, sin volver a pedir
// `GET /rfp/tickets` en cada evento.
function ticketDetailFromEvent(event: RfpTicketCreatedEvent): TicketDetail {
  return {
    ticket: {
      id: event.ticket_id,
      status: event.status,
      discard_reason: null,
      created_at: event.created_at,
      updated_at: event.created_at,
    },
    metadata: {
      client_name: event.client_name,
      client_country: event.client_country,
      services_requested: event.services_requested,
      monthly_volume: null,
      deadline: null,
      budget_range: null,
      departments_needed: [],
    },
    sections: [],
    final_document: null,
  };
}

function liveStatusLabel(state: RfpStreamState) {
  if (state.status === "open") return "En vivo";
  if (state.status === "connecting") return "Conectando...";
  if (state.status === "unauthorized") return "Sin sesion -- vuelve a iniciar sesion";
  return `Reconectando en ${Math.ceil(state.retryInMs / 1000)}s (intento ${state.attempt})`;
}

export function RfpIntakePanel() {
  const { authFetch } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [tickets, setTickets] = useState<TicketDetail[]>([]);
  const knownTicketIds = useRef<Set<number>>(new Set());
  const [newTicketIds, setNewTicketIds] = useState<Set<number>>(new Set());
  const [lastArrival, setLastArrival] = useState<RfpTicketCreatedEvent | null>(null);
  const [approvalsByTicket, setApprovalsByTicket] = useState<Record<number, PendingApproval[]>>({});
  const [reasonDrafts, setReasonDrafts] = useState<Record<string, string>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  function assignFile(file: File | null) {
    setSelectedFile(file);
    setErrorMessage(null);
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    assignFile(event.target.files?.[0] || null);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    assignFile(event.dataTransfer.files?.[0] || null);
  }

  const fetchTicket = useCallback(
    async (ticketId: number) => {
      const response = await authFetch(`/rfp/tickets/${ticketId}`);
      if (!response.ok) return null;
      return (await response.json()) as TicketDetail;
    },
    [authFetch]
  );

  const refreshTicketList = useCallback(async () => {
    const response = await authFetch("/rfp/tickets");
    if (!response.ok) return;
    const summaries = (await response.json()) as TicketDetail["ticket"][];
    const details = await Promise.all(summaries.map((summary) => fetchTicket(summary.id)));
    const loaded = details.filter((detail): detail is TicketDetail => detail !== null);
    for (const detail of loaded) knownTicketIds.current.add(detail.ticket.id);
    // Fusiona en vez de reemplazar: un ticket llegado por SSE mientras esta
    // respuesta viajaba no debe desaparecer de la UI (los tickets nunca se
    // borran, así que lo que no vino en `loaded` es siempre más nuevo).
    setTickets((prev) => {
      const loadedIds = new Set(loaded.map((detail) => detail.ticket.id));
      return [...prev.filter((detail) => !loadedIds.has(detail.ticket.id)), ...loaded];
    });
  }, [authFetch, fetchTicket]);

  useEffect(() => {
    void refreshTicketList();
  }, [refreshTicketList]);

  // Hito 10 Parte 1: un ticket nuevo llega por SSE. Dedupe por `ticket_id`
  // (`knownTicketIds`): el mismo ticket puede llegar por la lista inicial,
  // por un replay tras reconectar (Last-Event-ID) o porque lo subió esta
  // misma pestaña -- en cualquier caso aparece una sola vez en la UI.
  const onTicketCreated = useCallback((event: RfpTicketCreatedEvent) => {
    if (knownTicketIds.current.has(event.ticket_id)) return;
    knownTicketIds.current.add(event.ticket_id);
    setTickets((prev) =>
      prev.some((detail) => detail.ticket.id === event.ticket_id) ? prev : [ticketDetailFromEvent(event), ...prev]
    );
    setNewTicketIds((prev) => new Set(prev).add(event.ticket_id));
    setLastArrival(event);
  }, []);

  // Primera apertura del stream: un refresco de la lista cierra el hueco
  // entre la carga inicial y el momento en que el stream quedó escuchando.
  // Las reconexiones posteriores NO refrescan -- de eso se encarga el
  // replay por Last-Event-ID en el servidor.
  const streamState = useRfpTicketStream({ onTicketCreated, onFirstOpen: () => void refreshTicketList() });

  function dismissNewTickets() {
    setNewTicketIds(new Set());
    setLastArrival(null);
  }

  // Polling: mientras haya tickets en "analizando", refresca cada 2s SOLO
  // esos tickets (no la lista entera) -- CONTEXT9.md: "la UI consulta/refresca
  // estado (analizando -> analisis_completo o descartado)". El stream SSE
  // anuncia la llegada; el avance de estado posterior sigue por acá.
  useEffect(() => {
    const analyzingIds = tickets
      .filter((detail) => detail.ticket.status === "analizando")
      .map((detail) => detail.ticket.id);
    if (analyzingIds.length === 0) return;

    const interval = setInterval(() => {
      void (async () => {
        const refreshed = await Promise.all(analyzingIds.map((id) => fetchTicket(id)));
        const byId = new Map(
          refreshed.filter((detail): detail is TicketDetail => detail !== null).map((detail) => [detail.ticket.id, detail])
        );
        setTickets((prev) => prev.map((detail) => byId.get(detail.ticket.id) ?? detail));
      })();
    }, 2000);
    return () => clearInterval(interval);
  }, [tickets, fetchTicket]);

  const loadApprovalRound = useCallback(
    async (ticketId: number) => {
      const response = await authFetch(`/rfp/tickets/${ticketId}/approval/start`, { method: "POST" });
      const data = (await response.json().catch(() => null)) as ApprovalRoundState | { detail?: string } | null;
      if (!response.ok) {
        setActionError((data as { detail?: string } | null)?.detail || "No se pudo cargar la ronda de aprobacion.");
        return;
      }
      const roundState = data as ApprovalRoundState;
      setApprovalsByTicket((prev) => ({ ...prev, [ticketId]: roundState.pending_approvals }));
      await refreshTicketList();
    },
    [authFetch, refreshTicketList]
  );

  // Hito 9 Parte 3: un ticket "esperando_aprobación" ya tiene una ronda en
  // curso -- la UI la carga sola (misma llamada que "arrancarla", es
  // idempotente, ver `pipeline.py::start_or_get_approval_round`).
  useEffect(() => {
    for (const detail of tickets) {
      if (detail.ticket.status === "esperando_aprobación" && !approvalsByTicket[detail.ticket.id]) {
        void loadApprovalRound(detail.ticket.id);
      }
    }
  }, [tickets, approvalsByTicket, loadApprovalRound]);

  async function triggerGeneration(ticketId: number) {
    setBusyAction(`generate:${ticketId}`);
    setActionError(null);
    try {
      const response = await authFetch(`/rfp/tickets/${ticketId}/generate`, { method: "POST" });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setActionError(data?.detail || "No se pudo generar la propuesta.");
        return;
      }
      await refreshTicketList();
    } finally {
      setBusyAction(null);
    }
  }

  async function submitDecision(
    ticketId: number,
    departmentId: string,
    decision: "approve" | "reject" | "request_changes"
  ) {
    const reasonKey = `${ticketId}:${departmentId}`;
    const reason = reasonDrafts[reasonKey]?.trim() || null;
    setBusyAction(`${decision}:${ticketId}:${departmentId}`);
    setActionError(null);
    try {
      const response = await authFetch(`/rfp/tickets/${ticketId}/approval/${departmentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason }),
      });
      const data = (await response.json().catch(() => null)) as ApprovalRoundState | { detail?: string } | null;
      if (!response.ok) {
        setActionError((data as { detail?: string } | null)?.detail || "No se pudo registrar la decision.");
        return;
      }
      const roundState = data as ApprovalRoundState;
      setApprovalsByTicket((prev) => ({ ...prev, [ticketId]: roundState.pending_approvals }));
      setReasonDrafts((prev) => ({ ...prev, [reasonKey]: "" }));
      await refreshTicketList();
    } finally {
      setBusyAction(null);
    }
  }

  async function submitFile() {
    if (!selectedFile) {
      setErrorMessage("Selecciona un PDF antes de subir la RFP.");
      return;
    }

    const payload = new FormData();
    payload.append("file", selectedFile);

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await authFetch("/rfp/tickets", { method: "POST", body: payload });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setErrorMessage(data?.detail || "No se pudo subir la RFP.");
        return;
      }

      setSelectedFile(null);
      await refreshTicketList();
    } catch {
      setErrorMessage("No se pudo conectar con la API para subir la RFP.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="analysis-grid">
      <section className="card analysis-intro-card">
        <div className="eyebrow">Hito 09 - Parte 1 - Recepcion de RFPs</div>
        <h2 className="panel-title">Sube una RFP en PDF y segui su ticket en tiempo real</h2>
        <p className="analysis-copy">
          Se crea un ticket por cada PDF subido. El analisis (conversion, clasificacion, y reparto
          por departamento) corre en segundo plano -- esta pantalla se refresca sola mientras el
          ticket esta en &quot;Analizando...&quot;.
        </p>

        <label
          className={dragActive ? "upload-dropzone drag-active" : "upload-dropzone"}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
        >
          <input type="file" accept=".pdf,application/pdf" onChange={onFileChange} className="sr-only" />
          <span className="upload-kicker">PDF / multipart</span>
          <strong>{selectedFile ? selectedFile.name : "Arrastra tu RFP en PDF aqui"}</strong>
          <span>
            {selectedFile
              ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB listos para enviar`
              : "o haz clic para seleccionarlo desde tu equipo"}
          </span>
        </label>

        <div className="analysis-actions">
          <button type="button" className="primary-button" onClick={submitFile} disabled={isSubmitting}>
            {isSubmitting ? "Subiendo..." : "Subir RFP"}
          </button>
        </div>

        {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}
      </section>

      <section className="card analysis-summary-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Tickets</h3>
            <p className="section-caption">Mas reciente primero. Las RFP nuevas aparecen solas, sin recargar.</p>
          </div>
          <span className="rfp-live-pill" data-state={streamState.status} role="status">
            {liveStatusLabel(streamState)}
          </span>
        </div>

        <div aria-live="polite">
          {lastArrival ? (
            <div className="rfp-arrival-banner">
              <span>
                <strong>Nueva RFP{newTicketIds.size > 1 ? ` (+${newTicketIds.size - 1} mas)` : ""}:</strong>{" "}
                Ticket #{lastArrival.ticket_id}
                {lastArrival.client_name ? ` -- ${lastArrival.client_name}` : ""}
                {lastArrival.client_country ? ` (${lastArrival.client_country})` : ""}
                {lastArrival.services_requested.length > 0
                  ? ` -- ${lastArrival.services_requested.map((id) => DEPARTMENT_LABELS[id] ?? id).join(", ")}`
                  : ""}
              </span>
              <button type="button" className="secondary-button" onClick={dismissNewTickets}>
                Marcar como vistas
              </button>
            </div>
          ) : null}
        </div>

        {tickets.length === 0 ? (
          <p className="section-caption">Todavia no subiste ninguna RFP.</p>
        ) : (
          <ul className="summary-list">
            {tickets.map((detail) => (
              <li
                key={detail.ticket.id}
                className={newTicketIds.has(detail.ticket.id) ? "rfp-ticket-new" : undefined}
                style={{ flexDirection: "column", alignItems: "stretch", gap: "0.5rem" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>
                    {newTicketIds.has(detail.ticket.id) ? <span className="rfp-new-badge">Nueva</span> : null}
                    Ticket #{detail.ticket.id}
                    {detail.metadata?.client_name ? ` -- ${detail.metadata.client_name}` : ""}
                  </span>
                  <span className={statusBadgeClass(detail.ticket.status)}>
                    {STATUS_LABELS[detail.ticket.status] ?? detail.ticket.status}
                  </span>
                </div>

                {detail.ticket.status === "descartado" && detail.ticket.discard_reason ? (
                  <p className="feedback-error" style={{ margin: 0 }}>
                    {detail.ticket.discard_reason}
                  </p>
                ) : null}

                {detail.metadata ? (
                  <div className="section-caption">
                    <div>
                      Pais: {detail.metadata.client_country ?? "N/D"} - Volumen mensual:{" "}
                      {detail.metadata.monthly_volume ?? "N/D"} - Departamentos:{" "}
                      {detail.metadata.departments_needed.map((id) => DEPARTMENT_LABELS[id] ?? id).join(", ") || "N/D"}
                    </div>
                  </div>
                ) : null}

                {detail.sections.length > 0 ? (
                  <ul className="summary-list summary-list-compact">
                    {detail.sections.map((section) => (
                      <li key={section.department_id}>
                        <span>{DEPARTMENT_LABELS[section.department_id] ?? section.department_id}</span>
                        <strong>
                          {section.approval_status
                            ? `${section.approval_status}${section.approver ? ` -- ${section.approver}` : ""}`
                            : `${Object.keys(section.key_aspects).length} aspectos clave`}
                        </strong>
                      </li>
                    ))}
                  </ul>
                ) : null}

                {detail.ticket.status === "analisis_completo" ? (
                  <div className="analysis-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => triggerGeneration(detail.ticket.id)}
                      disabled={busyAction === `generate:${detail.ticket.id}`}
                    >
                      {busyAction === `generate:${detail.ticket.id}` ? "Generando..." : "Generar propuesta"}
                    </button>
                  </div>
                ) : null}

                {detail.ticket.status === "en_evaluación" || detail.ticket.status === "needs_human_review" ? (
                  <div className="analysis-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => loadApprovalRound(detail.ticket.id)}
                    >
                      Iniciar aprobacion por departamento
                    </button>
                  </div>
                ) : null}

                {detail.ticket.status === "esperando_aprobación" && approvalsByTicket[detail.ticket.id] ? (
                  <div className="section-caption" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <strong>Aprobacion pendiente por departamento</strong>
                    {approvalsByTicket[detail.ticket.id].length === 0 ? (
                      <span>Sin aprobaciones pendientes -- actualizando...</span>
                    ) : (
                      approvalsByTicket[detail.ticket.id].map((approval) => {
                        const reasonKey = `${detail.ticket.id}:${approval.department_id}`;
                        return (
                          <div
                            key={approval.department_id}
                            style={{ border: "1px solid var(--border, #333)", borderRadius: "8px", padding: "0.75rem" }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <strong>{DEPARTMENT_LABELS[approval.department_id] ?? approval.department_id}</strong>
                              <span>Responsable: {approval.approver}</span>
                            </div>
                            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>{approval.draft_content}</pre>
                            <textarea
                              placeholder="Motivo (obligatorio para rechazar / pedir cambios)"
                              value={reasonDrafts[reasonKey] ?? ""}
                              onChange={(event) =>
                                setReasonDrafts((prev) => ({ ...prev, [reasonKey]: event.target.value }))
                              }
                              style={{ width: "100%", minHeight: "3rem" }}
                            />
                            <div className="analysis-actions">
                              <button
                                type="button"
                                className="primary-button"
                                disabled={busyAction === `approve:${detail.ticket.id}:${approval.department_id}`}
                                onClick={() => submitDecision(detail.ticket.id, approval.department_id, "approve")}
                              >
                                Aprobar
                              </button>
                              <button
                                type="button"
                                className="secondary-button"
                                disabled={busyAction === `request_changes:${detail.ticket.id}:${approval.department_id}`}
                                onClick={() => submitDecision(detail.ticket.id, approval.department_id, "request_changes")}
                              >
                                Pedir cambios
                              </button>
                              <button
                                type="button"
                                className="secondary-button"
                                disabled={busyAction === `reject:${detail.ticket.id}:${approval.department_id}`}
                                onClick={() => submitDecision(detail.ticket.id, approval.department_id, "reject")}
                              >
                                Rechazar
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                ) : null}

                {detail.ticket.status === "terminado" && detail.final_document ? (
                  <div className="section-caption">
                    <strong>Documento final ({detail.final_document.currency})</strong>
                    {Object.entries(detail.final_document.sections).map(([departmentId, content]) => (
                      <details key={departmentId}>
                        <summary>{DEPARTMENT_LABELS[departmentId] ?? departmentId}</summary>
                        <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>{content}</pre>
                      </details>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {actionError ? <p className="feedback-error">{actionError}</p> : null}
      </section>
    </div>
  );
}
