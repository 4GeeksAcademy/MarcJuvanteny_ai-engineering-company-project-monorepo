import {
  STAGES,
  STATUSES,
  type CandidateStage,
  type CandidateStatus,
} from "@/types/candidate";

// Los valores en inglés de la API nunca se muestran: toda la UI pasa por aquí.
export const STATUS_LABELS: Record<CandidateStatus, string> = {
  received: "Recibida",
  in_progress: "En proceso",
  selected: "Seleccionada",
  discarded: "Descartada",
};

export const STAGE_LABELS: Record<CandidateStage, string> = {
  pending: "Pendiente de revisión",
  review: "En revisión",
  personal_interview: "Entrevista personal",
  technical_interview: "Entrevista técnica",
  offer_presented: "Oferta presentada",
};

export const STATUS_OPTIONS = STATUSES.map((value) => ({ value, label: STATUS_LABELS[value] }));
export const STAGE_OPTIONS = STAGES.map((value) => ({ value, label: STAGE_LABELS[value] }));

export function isStatus(value: string | null): value is CandidateStatus {
  return value !== null && (STATUSES as readonly string[]).includes(value);
}

export function isStage(value: string | null): value is CandidateStage {
  return value !== null && (STAGES as readonly string[]).includes(value);
}

// Si la API devolviera un valor nuevo, se muestra un texto neutro en lugar del valor crudo.
export function statusLabel(value: string): string {
  return isStatus(value) ? STATUS_LABELS[value] : "Estado desconocido";
}

export function stageLabel(value: string): string {
  return isStage(value) ? STAGE_LABELS[value] : "Etapa desconocida";
}

export const DEFAULT_POSITION = "Asistente de Dirección - Sede Zaragoza";

const dateFormatter = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "-" : dateFormatter.format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "-" : dateTimeFormatter.format(date);
}
