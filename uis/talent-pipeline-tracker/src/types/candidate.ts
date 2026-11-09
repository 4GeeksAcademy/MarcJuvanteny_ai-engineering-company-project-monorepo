// Contrato de la API mock del curso (https://playground.4geeks.com/tracker/api/v1/docs).
// Las formas de las respuestas de listado y de notas no están en el OpenAPI:
// se tomaron de llamadas reales a la API.

export const STATUSES = ["received", "in_progress", "selected", "discarded"] as const;
export const STAGES = [
  "pending",
  "review",
  "personal_interview",
  "technical_interview",
  "offer_presented",
] as const;

export type CandidateStatus = (typeof STATUSES)[number];
export type CandidateStage = (typeof STAGES)[number];

export type Note = {
  id: string;
  record_id: string;
  content: string;
  created_at: string;
};

// RecordOut. El listado incluye también `notes`, pero no se usa fuera del
// detalle (criterio de aceptación: las notas solo se ven en el detalle).
export type Candidate = {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  position: string;
  linkedin_url: string | null;
  cv_url: string | null;
  status: CandidateStatus;
  stage: CandidateStage;
  experience_years: number;
  notes_count: number;
  applied_at: string;
  updated_at: string;
};

// RecordCreate: mismo esquema para POST (alta) y PUT (edición).
export type CandidateInput = {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  experience_years: number;
  linkedin_url: string | null;
  cv_url: string | null;
};

// RecordPatch
export type CandidatePatch = {
  status?: CandidateStatus;
  stage?: CandidateStage;
};

export type CandidateFilters = {
  status?: CandidateStatus;
  stage?: CandidateStage;
  search?: string;
  page?: number;
  limit?: number;
};

// GET /records
export type CandidatePage = {
  total: number;
  page: number;
  limit: number;
  data: Candidate[];
};

// GET /records/{id}/notes
export type NoteList = {
  data: Note[];
  meta: { total: number };
};
