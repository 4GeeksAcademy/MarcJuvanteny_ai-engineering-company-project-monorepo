"use client";

import { useState } from "react";

import { InlineError, SuccessMessage } from "@/components/feedback";
import { errorMessage, patchCandidate } from "@/lib/api";
import { STAGE_OPTIONS, STATUS_OPTIONS, isStage, isStatus } from "@/lib/labels";
import type { Candidate } from "@/types/candidate";

type StatusStageEditorProps = {
  candidate: Candidate;
  onUpdated: (candidate: Candidate) => void;
};

export function StatusStageEditor({ candidate, onUpdated }: StatusStageEditorProps) {
  const [status, setStatus] = useState<string>(candidate.status);
  const [stage, setStage] = useState<string>(candidate.stage);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const dirty = status !== candidate.status || stage !== candidate.stage;

  async function save() {
    if (!isStatus(status) || !isStage(stage)) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await patchCandidate(candidate.id, { status, stage });
      onUpdated(updated);
      setSuccess("Estado y etapa actualizados.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const selectClass = "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

  return (
    <section aria-labelledby="pipeline-heading" className="grid gap-3 rounded-lg border border-slate-200 bg-white p-5">
      <h2 id="pipeline-heading" className="text-base font-semibold text-slate-900">
        Proceso de selección
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Estado
          <select value={status} onChange={(event) => setStatus(event.target.value)} disabled={saving} className={selectClass}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Etapa
          <select value={stage} onChange={(event) => setStage(event.target.value)} disabled={saving} className={selectClass}>
            {STAGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <InlineError message={error} />
      <SuccessMessage message={success} />
      <div className="flex justify-end gap-2">
        {dirty ? (
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              setStatus(candidate.status);
              setStage(candidate.stage);
            }}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Descartar cambios
          </button>
        ) : null}
        <button type="button" onClick={save} disabled={!dirty || saving} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
          {saving ? "Guardando..." : "Guardar cambios"}
        </button>
      </div>
    </section>
  );
}
