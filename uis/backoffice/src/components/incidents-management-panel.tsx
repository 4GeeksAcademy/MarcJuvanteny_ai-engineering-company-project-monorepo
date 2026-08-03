"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/lib/auth-context";

// Only 3 of the 9 Hito 10 incident categories are confirmed (memory-bank/progress.md).
// Extend this list once the remaining 6 are defined in the real Hito 10 CONTEXT.
const categoryOptions = ["lost_parcel", "carrier_issue", "inventory_discrepancy"] as const;
const categoryLabels: Record<string, string> = {
  lost_parcel: "Paquete perdido",
  carrier_issue: "Incidencia de transportista",
  inventory_discrepancy: "Discrepancia de inventario",
};

const originOptions = ["customer", "branch", "internal"] as const;
const originLabels: Record<string, string> = {
  customer: "Cliente",
  branch: "Sede",
  internal: "Interno",
};

const branchOptions = ["la_warehouse", "la_office", "zaragoza_warehouse", "zaragoza_office", "central"] as const;
const branchLabels: Record<string, string> = {
  la_warehouse: "LA Almacen",
  la_office: "LA Oficina",
  zaragoza_warehouse: "Zaragoza Almacen",
  zaragoza_office: "Zaragoza Oficina",
  central: "Central",
};

const statusOptions = ["open", "in_progress", "resolved", "discarded"] as const;
const statusLabels: Record<string, string> = {
  open: "Abierta",
  in_progress: "En curso",
  resolved: "Resuelta",
  discarded: "Descartada",
};

const statusBadgeClass: Record<string, string> = {
  open: "status-badge status-badge-open",
  in_progress: "status-badge status-badge-in-progress",
  resolved: "status-badge status-badge-resolved",
  discarded: "status-badge status-badge-discarded",
};

const nextStatusOptions: Record<string, string[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded"],
  resolved: [],
  discarded: [],
};

type IncidentStatus = (typeof statusOptions)[number];

type IncidentRecord = {
  id: number;
  title: string;
  description: string;
  category: string;
  origin: (typeof originOptions)[number];
  branch: string;
  status: IncidentStatus;
  source_incident_id: string | null;
  created_at: string;
  updated_at: string;
};

type IncidentSummary = {
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
};

type FormState = {
  title: string;
  description: string;
  category: string;
  origin: (typeof originOptions)[number];
  branch: string;
};

const initialFormState: FormState = {
  title: "",
  description: "",
  category: categoryOptions[0],
  origin: "customer",
  branch: "central",
};

type ApiErrorPayload = { detail?: string; field?: string };

function getGeneralErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const payload = data as ApiErrorPayload;
    if (payload.field) {
      return "Revisa el campo senalado en el formulario.";
    }
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  }
  return fallback;
}

function getFieldErrorMessage(data: unknown, field: string): string | undefined {
  if (data && typeof data === "object") {
    const payload = data as ApiErrorPayload;
    if (payload.field === field && typeof payload.detail === "string") {
      return payload.detail;
    }
  }
  return undefined;
}

function buildIncidentsQuery(status: string, origin: string, branch: string) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (origin) params.set("origin", origin);
  if (branch) params.set("branch", branch);
  const queryString = params.toString();
  return queryString ? `?${queryString}` : "";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

type AuthFetch = (path: string, options?: RequestInit) => Promise<Response>;

async function requestIncidents(authFetch: AuthFetch, status: string, origin: string, branch: string) {
  const response = await authFetch(`/api/incidents${buildIncidentsQuery(status, origin, branch)}`, {
    cache: "no-store",
  });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(getGeneralErrorMessage(data, "No se pudo cargar el listado de incidencias."));
  }

  return (data ?? []) as IncidentRecord[];
}

async function requestSummary(authFetch: AuthFetch) {
  const response = await authFetch("/api/incidents/summary", { cache: "no-store" });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(getGeneralErrorMessage(data, "No se pudieron cargar las metricas de incidencias."));
  }

  return data as IncidentSummary;
}

export function IncidentsManagementPanel() {
  const { authFetch } = useAuth();

  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const [incidents, setIncidents] = useState<IncidentRecord[]>([]);
  const [selectedStatus, setSelectedStatus] = useState("");
  const [selectedOrigin, setSelectedOrigin] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("");
  const [isListLoading, setIsListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [updatingIds, setUpdatingIds] = useState<number[]>([]);

  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  async function refreshIncidents(status = selectedStatus, origin = selectedOrigin, branch = selectedBranch) {
    setIsListLoading(true);
    setListError(null);

    try {
      const nextIncidents = await requestIncidents(authFetch, status, origin, branch);
      setIncidents(nextIncidents);
    } catch (error) {
      setIncidents([]);
      setListError(error instanceof Error ? error.message : "No se pudo conectar con la API de incidencias.");
    } finally {
      setIsListLoading(false);
    }
  }

  async function refreshSummary() {
    setIsSummaryLoading(true);
    setSummaryError(null);

    try {
      const nextSummary = await requestSummary(authFetch);
      setSummary(nextSummary);
    } catch (error) {
      setSummary(null);
      setSummaryError(error instanceof Error ? error.message : "No se pudo conectar con la API de incidencias.");
    } finally {
      setIsSummaryLoading(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshIncidents(selectedStatus, selectedOrigin, selectedBranch);
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStatus, selectedOrigin, selectedBranch, authFetch]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshSummary();
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch]);

  const totalVisible = incidents.length;

  const summaryRows = useMemo(() => {
    if (!summary) return null;
    return {
      status: statusOptions.map((status) => ({ key: status, label: statusLabels[status], count: summary.by_status?.[status] ?? 0 })),
      category: categoryOptions.map((category) => ({ key: category, label: categoryLabels[category], count: summary.by_category?.[category] ?? 0 })),
      origin: originOptions.map((origin) => ({ key: origin, label: originLabels[origin], count: summary.by_origin?.[origin] ?? 0 })),
      branch: branchOptions.map((branch) => ({ key: branch, label: branchLabels[branch], count: summary.by_branch?.[branch] ?? 0 })),
    };
  }, [summary]);

  async function submitIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    setFieldErrors({});

    const payload = {
      title: formState.title.trim(),
      description: formState.description.trim(),
      category: formState.category,
      origin: formState.origin,
      branch: formState.branch,
    };

    try {
      const response = await authFetch("/api/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const field = data && typeof data === "object" ? (data as ApiErrorPayload).field : undefined;
        if (field) {
          setFieldErrors({ [field]: getFieldErrorMessage(data, field) || "Valor no valido." });
        } else {
          setSubmitError(getGeneralErrorMessage(data, "La API rechazo el registro de la incidencia."));
        }
        return;
      }

      setFormState(initialFormState);
      setSubmitSuccess("Incidencia registrada correctamente.");
      await refreshIncidents();
      await refreshSummary();
    } catch {
      setSubmitError("No se pudo registrar la incidencia en la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function updateIncidentStatus(incident: IncidentRecord, nextStatus: string) {
    const previousStatus = incident.status;
    setUpdatingIds((current) => [...current, incident.id]);
    setIncidents((current) => current.map((item) => (item.id === incident.id ? { ...item, status: nextStatus as IncidentStatus } : item)));
    setListError(null);

    try {
      const response = await authFetch(`/api/incidents/${incident.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setIncidents((current) => current.map((item) => (item.id === incident.id ? { ...item, status: previousStatus } : item)));
        setListError(getGeneralErrorMessage(data, "No se pudo actualizar el estado de la incidencia."));
        return;
      }

      const updatedIncident = data as IncidentRecord;
      setIncidents((current) => current.map((item) => (item.id === incident.id ? updatedIncident : item)));
      await refreshSummary();
    } catch {
      setIncidents((current) => current.map((item) => (item.id === incident.id ? { ...item, status: previousStatus } : item)));
      setListError("No se pudo conectar con la API para actualizar el estado.");
    } finally {
      setUpdatingIds((current) => current.filter((id) => id !== incident.id));
    }
  }

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Hito 10 · Gestor de incidencias centralizado</div>
          <h2 className="panel-title">Registra, filtra y resuelve incidencias operativas desde un unico panel</h2>
          <p className="analysis-copy">
            Cubre clientes, sedes e incidencias internas con un ciclo de vida controlado: abierta, en curso, resuelta o descartada.
          </p>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Resumen agregado</h3>
            <p className="section-caption">Metricas de GET /api/incidents/summary por estado, categoria, origen y sede.</p>
          </div>
        </div>

        {isSummaryLoading ? <p className="empty-state-inline">Cargando metricas...</p> : null}
        {!isSummaryLoading && summaryError ? (
          <p className="feedback-error">
            {summaryError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void refreshSummary()}>
              Reintentar
            </button>
          </p>
        ) : null}

        {!isSummaryLoading && summaryRows ? (
          <div className="suppliers-summary-strip" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
            <article className="supplier-stat-card">
              <span>Por estado</span>
              <div className="category-chip-list">
                {summaryRows.status.map((row) => (
                  <span key={row.key} className="category-chip">{row.label}: {row.count}</span>
                ))}
              </div>
            </article>
            <article className="supplier-stat-card">
              <span>Por categoria</span>
              <div className="category-chip-list">
                {summaryRows.category.map((row) => (
                  <span key={row.key} className="category-chip">{row.label}: {row.count}</span>
                ))}
              </div>
            </article>
            <article className="supplier-stat-card">
              <span>Por origen</span>
              <div className="category-chip-list">
                {summaryRows.origin.map((row) => (
                  <span key={row.key} className="category-chip">{row.label}: {row.count}</span>
                ))}
              </div>
            </article>
            <article className="supplier-stat-card">
              <span>Por sede</span>
              <div className="category-chip-list">
                {summaryRows.branch.map((row) => (
                  <span key={row.key} className="category-chip">{row.label}: {row.count}</span>
                ))}
              </div>
            </article>
          </div>
        ) : null}
      </section>

      <section className="card suppliers-toolbar-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Filtros operativos</h3>
            <p className="section-caption">El listado se refresca automaticamente al cambiar estado, origen o sede.</p>
          </div>
        </div>

        <div className="suppliers-filters-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
          <label className="field-block">
            <span>Estado</span>
            <select value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)}>
              <option value="">Todos</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>{statusLabels[status]}</option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span>Origen</span>
            <select value={selectedOrigin} onChange={(event) => setSelectedOrigin(event.target.value)}>
              <option value="">Todos</option>
              {originOptions.map((origin) => (
                <option key={origin} value={origin}>{originLabels[origin]}</option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span>Sede</span>
            <select value={selectedBranch} onChange={(event) => setSelectedBranch(event.target.value)}>
              <option value="">Todas</option>
              {branchOptions.map((branch) => (
                <option key={branch} value={branch}>{branchLabels[branch]}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Listado de incidencias</h3>
            <p className="section-caption">Actualiza el estado directamente desde cada fila.</p>
          </div>
          <div className="summary-pill">{isListLoading ? "Cargando..." : `${totalVisible} incidencias`}</div>
        </div>

        {listError ? (
          <p className="feedback-error">
            {listError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void refreshIncidents()}>
              Reintentar
            </button>
          </p>
        ) : null}

        <div className="suppliers-table-wrap">
          <table className="suppliers-table">
            <thead>
              <tr>
                <th>Titulo</th>
                <th>Categoria</th>
                <th>Origen</th>
                <th>Sede</th>
                <th>Estado</th>
                <th>Actualizada</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((incident) => {
                const isUpdating = updatingIds.includes(incident.id);
                const nextOptions = nextStatusOptions[incident.status] ?? [];

                return (
                  <tr key={incident.id}>
                    <td>
                      <div className="supplier-name-cell">
                        <strong>{incident.title}</strong>
                        <span>{incident.description}</span>
                      </div>
                    </td>
                    <td>{categoryLabels[incident.category] ?? incident.category}</td>
                    <td>{originLabels[incident.origin] ?? incident.origin}</td>
                    <td>{branchLabels[incident.branch] ?? incident.branch}</td>
                    <td>
                      <span className={statusBadgeClass[incident.status]}>{statusLabels[incident.status]}</span>
                    </td>
                    <td>{formatDateTime(incident.updated_at)}</td>
                    <td>
                      {nextOptions.length ? (
                        <select
                          value=""
                          disabled={isUpdating}
                          onChange={(event) => {
                            if (event.target.value) {
                              void updateIncidentStatus(incident, event.target.value);
                            }
                          }}
                        >
                          <option value="">Cambiar estado...</option>
                          {nextOptions.map((option) => (
                            <option key={option} value={option}>{statusLabels[option]}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="section-caption">Estado final</span>
                      )}
                    </td>
                  </tr>
                );
              })}

              {!isListLoading && !listError && !incidents.length ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-state-inline">No hay incidencias para los filtros seleccionados.</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card supplier-form-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Registrar incidencia</h3>
            <p className="section-caption">El formulario consume POST /api/incidents y muestra el error de la API junto al campo afectado.</p>
          </div>
        </div>

        {submitError ? <p className="feedback-error">{submitError}</p> : null}
        {submitSuccess ? <p className="feedback-success">{submitSuccess}</p> : null}

        <form className="supplier-form-grid" onSubmit={(event) => void submitIncident(event)}>
          <label className="field-block field-block-wide">
            <span>Titulo</span>
            <input
              type="text"
              value={formState.title}
              onChange={(event) => setFormState((current) => ({ ...current, title: event.target.value }))}
              required
            />
            {fieldErrors.title ? <span className="feedback-error">{fieldErrors.title}</span> : null}
          </label>

          <label className="field-block field-block-wide">
            <span>Descripcion</span>
            <textarea
              rows={4}
              value={formState.description}
              onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))}
              required
            />
            {fieldErrors.description ? <span className="feedback-error">{fieldErrors.description}</span> : null}
          </label>

          <label className="field-block">
            <span>Categoria</span>
            <select
              value={formState.category}
              onChange={(event) => setFormState((current) => ({ ...current, category: event.target.value }))}
            >
              {categoryOptions.map((category) => (
                <option key={category} value={category}>{categoryLabels[category]}</option>
              ))}
            </select>
            {fieldErrors.category ? <span className="feedback-error">{fieldErrors.category}</span> : null}
          </label>

          <label className="field-block">
            <span>Origen</span>
            <select
              value={formState.origin}
              onChange={(event) => setFormState((current) => ({ ...current, origin: event.target.value as FormState["origin"] }))}
            >
              {originOptions.map((origin) => (
                <option key={origin} value={origin}>{originLabels[origin]}</option>
              ))}
            </select>
            {fieldErrors.origin ? <span className="feedback-error">{fieldErrors.origin}</span> : null}
          </label>

          <label className={formState.origin === "branch" ? "field-block field-block-wide field-block-highlight" : "field-block field-block-wide"}>
            <span>Sede {formState.origin === "branch" ? "(reportando desde una sede especifica)" : ""}</span>
            <select
              value={formState.branch}
              onChange={(event) => setFormState((current) => ({ ...current, branch: event.target.value }))}
              required
            >
              {branchOptions.map((branch) => (
                <option key={branch} value={branch}>{branchLabels[branch]}</option>
              ))}
            </select>
            {fieldErrors.branch ? <span className="feedback-error">{fieldErrors.branch}</span> : null}
          </label>

          <div className="supplier-form-actions field-block-wide">
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Registrando..." : "Registrar incidencia"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
