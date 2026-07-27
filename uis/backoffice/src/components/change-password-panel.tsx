"use client";

import { FormEvent, useState } from "react";

import { extractErrorMessage } from "@/lib/api-errors";
import { useAuth } from "@/lib/auth-context";

export function ChangePasswordPanel() {
  const { authFetch } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (newPassword !== confirmPassword) {
      setErrorMessage("Las contrasenas nuevas no coinciden.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await authFetch("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setErrorMessage(extractErrorMessage(data, "No se pudo actualizar la contrasena."));
        return;
      }

      setSuccessMessage("Contrasena actualizada correctamente.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      setErrorMessage("No se pudo conectar con la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="card">
      <div className="section-header-row">
        <div>
          <h3 className="panel-title">Cambiar contrasena</h3>
          <p className="section-caption">Verifica tu contrasena actual antes de establecer una nueva.</p>
        </div>
      </div>

      {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}
      {successMessage ? <p className="feedback-success">{successMessage}</p> : null}

      <form className="supplier-form-grid" onSubmit={(event) => void onSubmit(event)}>
        <label className="field-block">
          <span>Contrasena actual</span>
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            minLength={8}
            required
          />
        </label>

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
          <span>Confirmar nueva contrasena</span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </label>

        <div className="supplier-form-actions field-block-wide">
          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting ? "Actualizando..." : "Actualizar contrasena"}
          </button>
        </div>
      </form>
    </section>
  );
}
