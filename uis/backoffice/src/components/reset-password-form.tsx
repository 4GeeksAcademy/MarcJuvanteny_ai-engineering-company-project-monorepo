"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { extractErrorMessage } from "@/lib/api-errors";
import { API_BASE_URL } from "@/lib/auth";

export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);

    if (newPassword !== confirmPassword) {
      setErrorMessage("Las contrasenas no coinciden.");
      return;
    }

    if (!token) {
      setErrorMessage("El enlace de restablecimiento no es valido.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setErrorMessage(extractErrorMessage(data, "El enlace expiro o no es valido."));
        return;
      }

      router.replace("/login?resetSuccess=1");
    } catch {
      setErrorMessage("No se pudo conectar con la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="auth-page">
        <section className="card auth-card">
          <div className="eyebrow">TrackFlow Backoffice</div>
          <h1 className="panel-title">Enlace invalido</h1>
          <p className="feedback-error">El enlace de restablecimiento no es valido o esta incompleto.</p>
          <p className="auth-links">
            <Link href="/forgot-password">Solicitar un nuevo enlace</Link>
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <section className="card auth-card">
        <div className="eyebrow">TrackFlow Backoffice</div>
        <h1 className="panel-title">Restablecer contrasena</h1>
        <p className="section-caption">Introduce tu nueva contrasena para continuar.</p>

        <form className="auth-form" onSubmit={(event) => void onSubmit(event)}>
          <label className="field-block">
            <span>Nueva contrasena</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>

          <label className="field-block">
            <span>Confirmar contrasena</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </label>

          {errorMessage ? (
            <p className="feedback-error">
              {errorMessage} <Link href="/forgot-password">Solicitar un nuevo enlace</Link>
            </p>
          ) : null}

          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting ? "Actualizando..." : "Restablecer contrasena"}
          </button>
        </form>
      </section>
    </div>
  );
}
