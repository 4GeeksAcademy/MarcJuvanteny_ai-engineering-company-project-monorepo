"use client";

import { useState, type FormEvent } from "react";

import { InlineError } from "@/components/feedback";
import { errorMessage } from "@/lib/api";
import { DEFAULT_POSITION } from "@/lib/labels";
import type { Candidate, CandidateInput } from "@/types/candidate";

type FormValues = {
  full_name: string;
  email: string;
  phone: string;
  position: string;
  experience_years: string;
  linkedin_url: string;
  cv_url: string;
};

type CandidateFormProps = {
  initial?: Candidate;
  submitLabel: string;
  onSubmit: (input: CandidateInput) => Promise<void>;
  onCancel: () => void;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function toValues(candidate?: Candidate): FormValues {
  return {
    full_name: candidate?.full_name ?? "",
    email: candidate?.email ?? "",
    phone: candidate?.phone ?? "",
    position: candidate?.position ?? DEFAULT_POSITION,
    experience_years: candidate ? String(candidate.experience_years) : "",
    linkedin_url: candidate?.linkedin_url ?? "",
    cv_url: candidate?.cv_url ?? "",
  };
}

function isUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function validate(values: FormValues): Partial<Record<keyof FormValues, string>> {
  const errors: Partial<Record<keyof FormValues, string>> = {};
  if (!values.full_name.trim()) errors.full_name = "El nombre es obligatorio.";
  if (!EMAIL_RE.test(values.email.trim())) errors.email = "Introduce un email válido.";
  if (!values.phone.trim()) errors.phone = "El teléfono es obligatorio.";
  if (!values.position.trim()) errors.position = "El puesto es obligatorio.";
  const years = Number(values.experience_years);
  if (values.experience_years.trim() === "" || Number.isNaN(years) || years < 0) {
    errors.experience_years = "Indica los años de experiencia (0 o más).";
  }
  if (values.linkedin_url.trim() && !isUrl(values.linkedin_url.trim())) errors.linkedin_url = "Debe ser una URL (https://...).";
  if (values.cv_url.trim() && !isUrl(values.cv_url.trim())) errors.cv_url = "Debe ser una URL (https://...).";
  return errors;
}

export function CandidateForm({ initial, submitLabel, onSubmit, onCancel }: CandidateFormProps) {
  const [values, setValues] = useState<FormValues>(() => toValues(initial));
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function setField(field: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validate(values);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit({
        full_name: values.full_name.trim(),
        email: values.email.trim(),
        phone: values.phone.trim(),
        position: values.position.trim(),
        experience_years: Number(values.experience_years),
        linkedin_url: values.linkedin_url.trim() || null,
        cv_url: values.cv_url.trim() || null,
      });
    } catch (error) {
      setSubmitError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  const fields: { name: keyof FormValues; label: string; type: string; required: boolean; placeholder?: string }[] = [
    { name: "full_name", label: "Nombre completo", type: "text", required: true },
    { name: "email", label: "Email", type: "email", required: true },
    { name: "phone", label: "Teléfono", type: "tel", required: true, placeholder: "+34 600 000 000" },
    { name: "position", label: "Puesto", type: "text", required: true },
    { name: "experience_years", label: "Años de experiencia", type: "number", required: true },
    { name: "linkedin_url", label: "LinkedIn (opcional)", type: "url", required: false, placeholder: "https://linkedin.com/in/..." },
    { name: "cv_url", label: "URL del CV (opcional)", type: "url", required: false, placeholder: "https://..." },
  ];

  return (
    <form onSubmit={handleSubmit} noValidate className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((field) => {
          const error = fieldErrors[field.name];
          const id = `candidate-${field.name}`;
          return (
            <div key={field.name} className="grid gap-1">
              <label htmlFor={id} className="text-sm font-medium text-slate-700">
                {field.label}
                {field.required ? <span className="text-red-600"> *</span> : null}
              </label>
              <input
                id={id}
                type={field.type}
                value={values[field.name]}
                onChange={(event) => setField(field.name, event.target.value)}
                placeholder={field.placeholder}
                min={field.type === "number" ? 0 : undefined}
                step={field.type === "number" ? 0.5 : undefined}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? `${id}-error` : undefined}
                className={`rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
                  error ? "border-red-400 focus:ring-red-200" : "border-slate-300 focus:border-indigo-500 focus:ring-indigo-200"
                }`}
              />
              {error ? (
                <span id={`${id}-error`} className="text-xs text-red-700">
                  {error}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      <InlineError message={submitError} />

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={submitting} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50">
          Cancelar
        </button>
        <button type="submit" disabled={submitting} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
          {submitting ? "Guardando..." : submitLabel}
        </button>
      </div>
    </form>
  );
}
