"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { CandidateFilters } from "@/components/candidate-filters";
import { CandidateForm } from "@/components/candidate-form";
import { CandidateTable } from "@/components/candidate-table";
import { ErrorState, LoadingState, SuccessMessage } from "@/components/feedback";
import { Modal } from "@/components/modal";
import { Pagination } from "@/components/pagination";
import { createCandidate, errorMessage, listCandidates } from "@/lib/api";
import { isStage, isStatus } from "@/lib/labels";
import type { CandidateInput, CandidatePage } from "@/types/candidate";

const PAGE_SIZE = 20;

type ListResult = { key: string; page?: CandidatePage; error?: string };

export function CandidateList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Los filtros viven en la URL: se pueden compartir, recargar y usar con "atrás".
  // Valores no válidos en la URL se ignoran en lugar de mandarse a la API.
  const rawStatus = searchParams.get("status");
  const rawStage = searchParams.get("stage");
  const status = isStatus(rawStatus) ? rawStatus : undefined;
  const stage = isStage(rawStage) ? rawStage : undefined;
  const search = searchParams.get("search")?.trim() ?? "";
  const page = Math.max(1, Number.parseInt(searchParams.get("page") ?? "1", 10) || 1);

  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<ListResult | null>(null);
  const [creating, setCreating] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);

  const requestKey = JSON.stringify({ status, stage, search, page, attempt });
  const loading = result?.key !== requestKey;

  useEffect(() => {
    const controller = new AbortController();
    listCandidates({ status, stage, search: search || undefined, page, limit: PAGE_SIZE }, controller.signal)
      .then((data) => setResult({ key: requestKey, page: data }))
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ key: requestKey, error: errorMessage(error) });
      });
    return () => controller.abort();
  }, [requestKey, status, stage, search, page]);

  const updateUrl = useCallback(
    (changes: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [name, value] of Object.entries(changes)) {
        if (value) params.set(name, value);
        else params.delete(name);
      }
      // Cualquier cambio de filtro vuelve a la primera página.
      if (!("page" in changes)) params.delete("page");
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  async function handleCreate(input: CandidateInput) {
    const created = await createCandidate(input);
    setCreating(false);
    setSuccess(`Candidato "${created.full_name}" registrado correctamente.`);
    setTimeout(() => setSuccess(null), 4000);
    setAttempt((value) => value + 1);
  }

  const shown = result?.page;
  const totalPages = shown ? Math.max(1, Math.ceil(shown.total / PAGE_SIZE)) : 1;

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600" aria-live="polite">
          {shown && !result?.error ? `${shown.total} candidato${shown.total === 1 ? "" : "s"}` : " "}
          {loading && shown ? " · Actualizando..." : null}
        </p>
        <button type="button" onClick={() => setCreating(true)} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
          Nuevo candidato
        </button>
      </div>

      <SuccessMessage message={success} />

      <CandidateFilters
        status={status ?? ""}
        stage={stage ?? ""}
        search={search}
        onChange={updateUrl}
        onClear={() => router.replace(pathname, { scroll: false })}
      />

      {result?.error && !loading ? (
        <ErrorState message={result.error} onRetry={() => setAttempt((value) => value + 1)} />
      ) : shown ? (
        <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <CandidateTable candidates={shown.data} />
          <Pagination page={page} totalPages={totalPages} onPageChange={(next) => updateUrl({ page: next > 1 ? String(next) : undefined })} />
        </div>
      ) : (
        <LoadingState label="Cargando candidatos..." />
      )}

      {creating ? (
        <Modal title="Registrar candidato" onClose={() => setCreating(false)}>
          <CandidateForm submitLabel="Registrar candidato" onSubmit={handleCreate} onCancel={() => setCreating(false)} />
        </Modal>
      ) : null}
    </div>
  );
}
