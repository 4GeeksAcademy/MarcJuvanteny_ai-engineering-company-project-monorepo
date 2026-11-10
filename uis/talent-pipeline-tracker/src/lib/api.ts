import type {
  Candidate,
  CandidateFilters,
  CandidateInput,
  CandidatePage,
  CandidatePatch,
  Note,
  NoteList,
} from "@/types/candidate";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://playground.4geeks.com/tracker/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ValidationDetail = { loc?: (string | number)[]; msg?: string };

const FIELD_LABELS: Record<string, string> = {
  full_name: "Nombre completo",
  email: "Email",
  phone: "Teléfono",
  position: "Puesto",
  experience_years: "Años de experiencia",
  linkedin_url: "LinkedIn",
  cv_url: "CV",
  content: "Nota",
  status: "Estado",
  stage: "Etapa",
};

// La API responde `{ error: "..." }` (404) o `{ detail: [...] }` (422 de FastAPI).
function messageFromBody(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const { error, detail } = body as { error?: unknown; detail?: unknown };
    if (typeof error === "string") {
      return status === 404 ? "No se encontró el candidato o la nota solicitada." : error;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const fields = (detail as ValidationDetail[])
        .map((item) => String(item.loc?.[item.loc.length - 1] ?? ""))
        .map((field) => FIELD_LABELS[field] ?? field)
        .filter(Boolean);
      return `Revisa los campos: ${[...new Set(fields)].join(", ")}.`;
    }
  }
  if (status === 404) return "No se encontró el recurso solicitado.";
  if (status >= 500) return "La API no está disponible en este momento. Inténtalo de nuevo.";
  return `La API respondió con un error (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("No se pudo conectar con la API. Revisa tu conexión.", 0);
  }

  if (response.status === 204) return undefined as T;

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFromBody(body, response.status), response.status);
  return body as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ha ocurrido un error inesperado.";
}

export function listCandidates(filters: CandidateFilters, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.stage) params.set("stage", filters.stage);
  if (filters.search) params.set("search", filters.search);
  params.set("page", String(filters.page ?? 1));
  params.set("limit", String(filters.limit ?? 20));
  return request<CandidatePage>(`/records?${params}`, { signal });
}

export function getCandidate(id: string, signal?: AbortSignal) {
  return request<Candidate>(`/records/${encodeURIComponent(id)}`, { signal });
}

export function createCandidate(input: CandidateInput) {
  return request<Candidate>("/records", { method: "POST", body: JSON.stringify(input) });
}

export function updateCandidate(id: string, input: CandidateInput) {
  return request<Candidate>(`/records/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function patchCandidate(id: string, patch: CandidatePatch) {
  return request<Candidate>(`/records/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteCandidate(id: string) {
  return request<void>(`/records/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function listNotes(id: string, signal?: AbortSignal) {
  return request<NoteList>(`/records/${encodeURIComponent(id)}/notes`, { signal });
}

export function createNote(id: string, content: string) {
  return request<Note>(`/records/${encodeURIComponent(id)}/notes`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function deleteNote(id: string, noteId: string) {
  return request<void>(
    `/records/${encodeURIComponent(id)}/notes/${encodeURIComponent(noteId)}`,
    { method: "DELETE" },
  );
}
