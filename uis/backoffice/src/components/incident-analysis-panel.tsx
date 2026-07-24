"use client";

import { ChangeEvent, DragEvent, useMemo, useState } from "react";

import { useAuth } from "@/lib/auth-context";

type AnalysisSummary = {
  total_processed_incidents: number;
  total_valid_incidents: number;
  total_invalid_incidents: number;
  invalid_records_by_problem_type: Record<string, number>;
  incidents_by_category: Record<string, number>;
  incidents_by_status: Record<string, number>;
  incidents_by_country: Record<string, number>;
  average_satisfaction_closed_cases_with_score: number | null;
};

function formatEntries(record: Record<string, number>) {
  return Object.entries(record).sort((left, right) => right[1] - left[1]);
}

export function IncidentAnalysisPanel() {
  const { authFetch } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);

  const invalidEntries = useMemo(
    () => formatEntries(summary?.invalid_records_by_problem_type || {}),
    [summary]
  );
  const categoryEntries = useMemo(
    () => formatEntries(summary?.incidents_by_category || {}),
    [summary]
  );
  const statusEntries = useMemo(
    () => formatEntries(summary?.incidents_by_status || {}),
    [summary]
  );

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

  async function submitFile() {
    if (!selectedFile) {
      setErrorMessage("Selecciona un CSV antes de lanzar el analisis.");
      return;
    }

    const payload = new FormData();
    payload.append("file", selectedFile);

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await authFetch("/api/incidents/analyze", {
        method: "POST",
        body: payload,
      });

      const data = await response.json();
      if (!response.ok) {
        setSummary(null);
        setErrorMessage(data.detail || "No se pudo analizar el fichero.");
        return;
      }

      setSummary(data as AnalysisSummary);
    } catch {
      setSummary(null);
      setErrorMessage("No se pudo conectar con la API de incidencias.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function downloadResults() {
    setIsExporting(true);
    setErrorMessage(null);

    try {
      const response = await authFetch("/api/incidents/results/export");

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setErrorMessage(data?.detail || "No se pudo descargar el resultado.");
        return;
      }

      const blob = await response.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = "results.csv";
      link.click();
      URL.revokeObjectURL(downloadUrl);
    } catch {
      setErrorMessage("No se pudo conectar con la API para descargar el resultado.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="analysis-grid">
      <section className="card analysis-intro-card">
        <div className="eyebrow">Hito 07 · Analisis de incidencias</div>
        <h2 className="panel-title">Carga un CSV y analiza calidad y operacion en un solo paso</h2>
        <p className="analysis-copy">
          Arrastra el fichero exportado del helpdesk o selecciona un CSV manualmente. La vista
          consume el endpoint backend y muestra el resumen operativo, los invalidos y el indice de
          satisfaccion en cerrados.
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
          <input type="file" accept=".csv,text/csv" onChange={onFileChange} className="sr-only" />
          <span className="upload-kicker">CSV / multipart</span>
          <strong>{selectedFile ? selectedFile.name : "Arrastra tu CSV aqui"}</strong>
          <span>
            {selectedFile
              ? `${Math.max(1, Math.round(selectedFile.size / 1024))} KB listos para enviar`
              : "o haz clic para seleccionarlo desde tu equipo"}
          </span>
        </label>

        <div className="analysis-actions">
          <button type="button" className="primary-button" onClick={submitFile} disabled={isSubmitting}>
            {isSubmitting ? "Analizando..." : "Analizar incidencias"}
          </button>
          <button
            type="button"
            className={summary ? "secondary-button" : "secondary-button disabled"}
            aria-disabled={!summary}
            disabled={!summary || isExporting}
            onClick={() => void downloadResults()}
          >
            {isExporting ? "Descargando..." : "Descargar resultados CSV"}
          </button>
        </div>

        {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}
      </section>

      <section className="cards analysis-metrics">
        <article className="card metric-card">
          <h2>Total procesados</h2>
          <div className="metric">{summary?.total_processed_incidents ?? "-"}</div>
        </article>
        <article className="card metric-card">
          <h2>Validos</h2>
          <div className="metric">{summary?.total_valid_incidents ?? "-"}</div>
        </article>
        <article className="card metric-card">
          <h2>Invalidos</h2>
          <div className="metric">{summary?.total_invalid_incidents ?? "-"}</div>
        </article>
      </section>

      <section className="card analysis-summary-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Resumen de resultados</h3>
            <p className="section-caption">Metricas generales, categoria, estado e indice de satisfaccion.</p>
          </div>
          <div className="summary-pill">
            Satisfaccion cerrados: {summary?.average_satisfaction_closed_cases_with_score ?? "N/D"}
          </div>
        </div>

        <div className="summary-columns">
          <div>
            <h4 className="table-title">Por categoria</h4>
            <ul className="summary-list">
              {categoryEntries.length ? categoryEntries.map(([label, value]) => (
                <li key={label}><span>{label}</span><strong>{value}</strong></li>
              )) : <li><span>Sin datos</span><strong>-</strong></li>}
            </ul>
          </div>
          <div>
            <h4 className="table-title">Por estado</h4>
            <ul className="summary-list">
              {statusEntries.length ? statusEntries.map(([label, value]) => (
                <li key={label}><span>{label}</span><strong>{value}</strong></li>
              )) : <li><span>Sin datos</span><strong>-</strong></li>}
            </ul>
          </div>
        </div>
      </section>

      <section className="card analysis-invalid-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Registros invalidos</h3>
            <p className="section-caption">Se informa si el fichero contiene invalidos y cuantos hay de cada tipo.</p>
          </div>
          <div className={summary?.total_invalid_incidents ? "badge-warn" : "badge-ok"}>
            {summary ? `${summary.total_invalid_incidents} invalidos` : "Esperando analisis"}
          </div>
        </div>

        <ul className="summary-list summary-list-compact">
          {invalidEntries.length ? invalidEntries.map(([label, value]) => (
            <li key={label}><span>{label}</span><strong>{value}</strong></li>
          )) : <li><span>No se detectaron registros invalidos</span><strong>0</strong></li>}
        </ul>
      </section>
    </div>
  );
}
