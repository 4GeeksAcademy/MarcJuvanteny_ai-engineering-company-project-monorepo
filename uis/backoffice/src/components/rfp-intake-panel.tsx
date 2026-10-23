"use client";

import { ChangeEvent, DragEvent, useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth-context";

type TicketStatus = "analizando" | "descartado" | "analisis_completo" | string;

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
};

const STATUS_LABELS: Record<string, string> = {
  analizando: "Analizando...",
  descartado: "Descartado",
  analisis_completo: "Analisis completo",
};

const DEPARTMENT_LABELS: Record<string, string> = {
  warehouse: "Warehouse Operations",
  lastmile: "Last Mile and Carrier Management",
  reverse: "Reverse Logistics",
};

function statusBadgeClass(status: TicketStatus) {
  if (status === "analisis_completo") return "badge-ok";
  if (status === "descartado") return "badge-warn";
  return "badge-pending";
}

export function RfpIntakePanel() {
  const { authFetch } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [tickets, setTickets] = useState<TicketDetail[]>([]);
  const pollingTicketIds = useRef<Set<number>>(new Set());

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
    setTickets(details.filter((detail): detail is TicketDetail => detail !== null));
  }, [authFetch, fetchTicket]);

  useEffect(() => {
    void refreshTicketList();
  }, [refreshTicketList]);

  // Polling: mientras haya tickets en "analizando", refresca cada 2s --
  // CONTEXT9.md: "la UI consulta/refresca estado (analizando -> analisis_completo o descartado)".
  useEffect(() => {
    const stillAnalyzing = tickets.some((detail) => detail.ticket.status === "analizando");
    if (!stillAnalyzing) return;

    const interval = setInterval(() => {
      void refreshTicketList();
    }, 2000);
    return () => clearInterval(interval);
  }, [tickets, refreshTicketList]);

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
            <p className="section-caption">Mas reciente primero. Click en un ticket para ver su detalle.</p>
          </div>
        </div>

        {tickets.length === 0 ? (
          <p className="section-caption">Todavia no subiste ninguna RFP.</p>
        ) : (
          <ul className="summary-list">
            {tickets.map((detail) => (
              <li key={detail.ticket.id} style={{ flexDirection: "column", alignItems: "stretch", gap: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span>
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
                        <strong>{Object.keys(section.key_aspects).length} aspectos clave</strong>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
