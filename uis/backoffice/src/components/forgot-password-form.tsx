"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { extractErrorMessage } from "@/lib/api-errors";
import { API_BASE_URL } from "@/lib/auth";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setErrorMessage(extractErrorMessage(data, "No se pudo procesar la solicitud."));
        return;
      }

      setIsSubmitted(true);
    } catch {
      setErrorMessage("No se pudo conectar con la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="card auth-card">
        <div className="eyebrow">TrackFlow Backoffice</div>
        <h1 className="panel-title">Recuperar contrasena</h1>
        <p className="section-caption">
          Introduce tu email corporativo y te enviaremos un enlace para restablecer tu contrasena.
        </p>

        {isSubmitted ? (
          <p className="feedback-success">
            Si esa direccion esta registrada, recibiras un enlace de restablecimiento en breve.
          </p>
        ) : (
          <form className="auth-form" onSubmit={(event) => void onSubmit(event)}>
            <label className="field-block">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>

            {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}

            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Enviando..." : "Enviar enlace"}
            </button>
          </form>
        )}

        <p className="auth-links">
          <Link href="/login">Volver a iniciar sesion</Link>
        </p>
      </section>
    </div>
  );
}
