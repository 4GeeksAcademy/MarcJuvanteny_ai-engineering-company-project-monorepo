"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

const navItems = [
  { href: "/", label: "Resumen", key: "summary" },
  { href: "/inventory/products", label: "Inventario", key: "inventory-products" },
  { href: "/incidents-analysis", label: "Analisis de incidencias", key: "incidents" },
  { href: "/incidents", label: "Gestion de incidencias", key: "incidents-management" },
  { href: "/suppliers", label: "Proveedores", key: "suppliers" },
  { href: "/knowledge", label: "Base de conocimiento", key: "knowledge" },
  { href: "/rfp", label: "Recepcion de RFPs", key: "rfp" },
  { href: "/account/profile", label: "Mi cuenta", key: "account" },
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
          {/* Mismo isotipo que el logo de uis/website. */}
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
              <rect x="0" y="0" width="48" height="48" fill="#d7dbe1" />
              <path d="M6 10H42V22H30V40H18V24L29 16H6Z" fill="#000b2a" />
              <path d="M18 10H30L24 16L18 22Z" fill="#e8640c" />
            </svg>
          </span>
          <span>
            Track<span className="brand-flow">Flow</span>
            <span className="brand-product">Backoffice</span>
          </span>
        </div>
        <nav>
          {navItems.map((item) => {
            const isActive = item.key === activeKey;
            const className = isActive ? "sidebar-item active" : "sidebar-item";

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
