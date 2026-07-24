"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

const navItems = [
  { href: "/", label: "Resumen", key: "summary" },
  { href: "/incidents-analysis", label: "Incidencias", key: "incidents" },
  { href: "/suppliers", label: "Proveedores", key: "suppliers" },
  { href: "/account/profile", label: "Mi cuenta", key: "account" },
  { href: "#", label: "Candidatos", key: "candidates" },
  { href: "#", label: "Pipeline", key: "pipeline" },
  { href: "#", label: "Configuracion", key: "settings" },
];

type BackofficeShellProps = {
  activeKey: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
};

export function BackofficeShell({ activeKey, title, subtitle, children }: BackofficeShellProps) {
  const { user, logout } = useAuth();
  const router = useRouter();

  function onLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div className="backoffice-shell">
      <aside className="sidebar" aria-label="Navegacion interna de backoffice">
        <div className="brand">
          TrackFlow <span>Backoffice</span>
        </div>
        <nav>
          {navItems.map((item) => {
            const isActive = item.key === activeKey;
            const className = isActive ? "sidebar-item active" : "sidebar-item";

            if (item.href === "#") {
              return (
                <span key={item.key} className={className} aria-current={isActive ? "page" : undefined}>
                  {item.label}
                </span>
              );
            }

            return (
              <Link key={item.key} href={item.href} className={className} aria-current={isActive ? "page" : undefined}>
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <section className="content">
        <header className="topbar">
          <div className="topbar-row">
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>

            <div className="topbar-session">
              {user ? <span className="topbar-email">{user.email}</span> : null}
              <button type="button" className="secondary-button compact-button" onClick={onLogout}>
                Cerrar sesion
              </button>
            </div>
          </div>
        </header>

        <main className="dashboard">{children}</main>
      </section>
    </div>
  );
}
