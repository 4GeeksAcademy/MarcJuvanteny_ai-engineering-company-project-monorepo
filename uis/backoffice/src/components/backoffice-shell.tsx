import Link from "next/link";

const navItems = [
  { href: "/", label: "Resumen", key: "summary" },
  { href: "/incidents-analysis", label: "Incidencias", key: "incidents" },
  { href: "/suppliers", label: "Proveedores", key: "suppliers" },
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
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </header>

        <main className="dashboard">{children}</main>
      </section>
    </div>
  );
}
