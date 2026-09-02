"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { extractErrorMessage, extractFieldErrors, FieldErrors } from "@/lib/api-errors";
import { API_BASE_URL } from "@/lib/auth";
import { useAuth } from "@/lib/auth-context";
import { timedFetch } from "@/services/telemetry";

type RegisterFormState = {
  email: string;
  password: string;
  confirmPassword: string;
  name: string;
  phone: string;
  address: string;
};

const initialFormState: RegisterFormState = {
  email: "",
  password: "",
  confirmPassword: "",
  name: "",
  phone: "",
  address: "",
};

export function RegisterForm() {
  const router = useRouter();
  const { login } = useAuth();
  const [formState, setFormState] = useState<RegisterFormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function updateField<K extends keyof RegisterFormState>(field: K, value: string) {
    setFormState((current) => ({ ...current, [field]: value }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});

    if (formState.password !== formState.confirmPassword) {
      setFieldErrors({ confirmPassword: "Las contrasenas no coinciden." });
      return;
    }

    setIsSubmitting(true);

    try {
      let response: Response;
      try {
        response = await timedFetch(
          "/users",
          () =>
            fetch(`${API_BASE_URL}/users`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                email: formState.email,
                password: formState.password,
                name: formState.name || undefined,
                phone: formState.phone || undefined,
                address: formState.address || undefined,
              }),
            }),
          { method: "POST", service: "incidents-api" }
        );
      } catch {
        throw new Error("No se pudo conectar con el servidor. Verifica tu conexion e intentalo de nuevo.");
      }

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
        const fieldLevelErrors = extractFieldErrors(detail);
        if (Object.keys(fieldLevelErrors).length) {
          setFieldErrors(fieldLevelErrors);
        } else {
          setFormError(extractErrorMessage(data, "No se pudo completar el registro."));
        }
        return;
      }

      await login(formState.email, formState.password, "register");
      router.replace("/");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "No se pudo conectar con la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="card auth-card auth-card-wide">
        <div className="eyebrow">TrackFlow Backoffice</div>
        <h1 className="panel-title">Crear cuenta</h1>
        <p className="section-caption">Registra tu acceso para operar incidencias y el directorio de proveedores.</p>

        <form className="auth-form auth-form-grid" onSubmit={(event) => void onSubmit(event)}>
          <label className="field-block">
            <span>Email</span>
            <input
              type="email"
              value={formState.email}
              onChange={(event) => updateField("email", event.target.value)}
              autoComplete="email"
              required
            />
            {fieldErrors.email ? <span className="field-error">{fieldErrors.email}</span> : null}
          </label>

          <label className="field-block">
            <span>Nombre</span>
            <input
              type="text"
              value={formState.name}
              onChange={(event) => updateField("name", event.target.value)}
              autoComplete="name"
            />
            {fieldErrors.name ? <span className="field-error">{fieldErrors.name}</span> : null}
          </label>

          <label className="field-block">
            <span>Contrasena</span>
            <input
              type="password"
              value={formState.password}
              onChange={(event) => updateField("password", event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
            {fieldErrors.password ? <span className="field-error">{fieldErrors.password}</span> : null}
          </label>

          <label className="field-block">
            <span>Confirmar contrasena</span>
            <input
              type="password"
              value={formState.confirmPassword}
              onChange={(event) => updateField("confirmPassword", event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
            {fieldErrors.confirmPassword ? <span className="field-error">{fieldErrors.confirmPassword}</span> : null}
          </label>

          <label className="field-block">
            <span>Telefono</span>
            <input
              type="text"
              value={formState.phone}
              onChange={(event) => updateField("phone", event.target.value)}
              autoComplete="tel"
            />
            {fieldErrors.phone ? <span className="field-error">{fieldErrors.phone}</span> : null}
          </label>

          <label className="field-block">
            <span>Direccion</span>
            <input
              type="text"
              value={formState.address}
              onChange={(event) => updateField("address", event.target.value)}
              autoComplete="street-address"
            />
            {fieldErrors.address ? <span className="field-error">{fieldErrors.address}</span> : null}
          </label>

          {formError ? <p className="feedback-error field-block-wide">{formError}</p> : null}

          <div className="field-block-wide">
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Creando cuenta..." : "Crear cuenta"}
            </button>
          </div>
        </form>

        <p className="auth-links">
          Ya tienes cuenta? <Link href="/login">Inicia sesion</Link>
        </p>
      </section>
    </div>
  );
}
