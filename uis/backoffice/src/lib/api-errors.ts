export type FieldErrors = Record<string, string>;

type PydanticErrorItem = { loc?: unknown[]; msg?: string };

export function extractFieldErrors(detail: unknown): FieldErrors {
  if (!Array.isArray(detail)) {
    return {};
  }

  const fieldErrors: FieldErrors = {};
  for (const item of detail as PydanticErrorItem[]) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const loc = Array.isArray(item.loc) ? item.loc : [];
    const field = loc.length ? String(loc[loc.length - 1]) : "form";
    if (typeof item.msg === "string") {
      fieldErrors[field] = item.msg;
    }
  }
  return fieldErrors;
}

export function extractErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0];
      if (first && typeof first === "object" && typeof (first as { msg?: unknown }).msg === "string") {
        return (first as { msg: string }).msg;
      }
    }
  }
  return fallback;
}
