"use client";

import { useEffect, useState } from "react";

import { STAGE_OPTIONS, STATUS_OPTIONS } from "@/lib/labels";

type CandidateFiltersProps = {
  status: string;
  stage: string;
  search: string;
  onChange: (changes: { status?: string; stage?: string; search?: string }) => void;
  onClear: () => void;
};

const SEARCH_DEBOUNCE_MS = 300;

export function CandidateFilters({ status, stage, search, onChange, onClear }: CandidateFiltersProps) {
  // El texto se guarda en local y se lleva a la URL con debounce: no se
  // pide a la API una vez por tecla y la página nunca se recarga.
  const [searchInput, setSearchInput] = useState(search);

  useEffect(() => {
    if (searchInput.trim() === search) return;
    const timer = setTimeout(() => onChange({ search: searchInput.trim() }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput, search, onChange]);

  const hasFilters = Boolean(status || stage || search || searchInput);
  const fieldClass = "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

  return (
    <form role="search" onSubmit={(event) => event.preventDefault()} className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
      <label className="grid gap-1 text-sm font-medium text-slate-700">
        Buscar
        <input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Nombre o email" className={fieldClass} />
      </label>

      <label className="grid gap-1 text-sm font-medium text-slate-700">
        Estado
        <select value={status} onChange={(event) => onChange({ status: event.target.value })} className={fieldClass}>
          <option value="">Todos</option>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="grid gap-1 text-sm font-medium text-slate-700">
        Etapa
        <select value={stage} onChange={(event) => onChange({ stage: event.target.value })} className={fieldClass}>
          <option value="">Todas</option>
          {STAGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        disabled={!hasFilters}
        onClick={() => {
          setSearchInput("");
          onClear();
        }}
        className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Limpiar filtros
      </button>
    </form>
  );
}
