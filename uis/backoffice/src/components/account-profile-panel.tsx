"use client";

import { FormEvent, useState } from "react";

import { extractErrorMessage } from "@/lib/api-errors";
import { useAuth } from "@/lib/auth-context";

type ProfileFormState = {
  name: string;
  phone: string;
  address: string;
};

export function AccountProfilePanel() {
  const { user, authFetch, refreshUser } = useAuth();
  // AuthGuard only renders this panel once `status === "authenticated"`, so `user` is already populated here.
  const [formState, setFormState] = useState<ProfileFormState>(() => ({
    name: user?.profile?.name || "",
    phone: user?.profile?.phone || "",
    address: user?.profile?.address || "",
  }));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await authFetch("/profiles/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formState.name || undefined,
          phone: formState.phone || undefined,
          address: formState.address || undefined,
        }),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setErrorMessage(extractErrorMessage(data, "No se pudo actualizar el perfil."));
        return;
      }

      await refreshUser();
      setSuccessMessage("Perfil actualizado correctamente.");
    } catch {
      setErrorMessage("No se pudo conectar con la API para actualizar el perfil.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="analysis-grid">
      <section className="card">
        <div className="eyebrow">Cuenta</div>
        <h2 className="panel-title">Datos de sesion</h2>
        <p className="section-caption">
          Email: <strong>{user?.email}</strong> · Rol: <strong>{user?.role}</strong>
        </p>
      </section>

      <section className="card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Editar perfil</h3>
            <p className="section-caption">
              Actualiza tu nombre y datos de contacto. Los cambios se guardan con PUT /profiles/me.
            </p>
          </div>
        </div>

        {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}
        {successMessage ? <p className="feedback-success">{successMessage}</p> : null}

        <form className="supplier-form-grid" onSubmit={(event) => void onSubmit(event)}>
          <label className="field-block">
            <span>Nombre</span>
            <input
              type="text"
              value={formState.name}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
            />
          </label>

          <label className="field-block">
            <span>Telefono</span>
            <input
              type="text"
              value={formState.phone}
              onChange={(event) => setFormState((current) => ({ ...current, phone: event.target.value }))}
            />
          </label>

          <label className="field-block field-block-wide">
            <span>Direccion</span>
            <input
              type="text"
              value={formState.address}
              onChange={(event) => setFormState((current) => ({ ...current, address: event.target.value }))}
            />
          </label>

          <div className="supplier-form-actions field-block-wide">
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Guardando..." : "Guardar cambios"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
