"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const resetSuccess = searchParams.get("resetSuccess") === "1";

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await login(email, password);
      router.replace("/");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "No se pudo iniciar sesion.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="card auth-card">
        <div className="eyebrow">TrackFlow Backoffice</div>
        <h1 className="panel-title">Iniciar sesion</h1>
        <p className="section-caption">Accede con tu email corporativo para gestionar incidencias y proveedores.</p>

        {resetSuccess ? (
          <p className="feedback-success">Tu contrasena se actualizo correctamente. Ya puedes iniciar sesion.</p>
        ) : null}

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

          <label className="field-block">
            <span>Contrasena</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              minLength={8}
              required
            />
          </label>

          <p className="auth-links">
            <Link href="/forgot-password">Olvidaste tu contrasena?</Link>
          </p>

          {errorMessage ? <p className="feedback-error">{errorMessage}</p> : null}

          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting ? "Accediendo..." : "Iniciar sesion"}
          </button>
        </form>

        <p className="auth-links">
          No tienes cuenta? <Link href="/register">Registrate</Link>
        </p>
      </section>
    </div>
  );
}
