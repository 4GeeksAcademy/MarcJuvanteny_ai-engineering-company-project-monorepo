import { BackofficeShell } from "@/components/backoffice-shell";
import { getHito2DashboardResult } from "@/lib/hito2";

export default function Home() {
  const result = getHito2DashboardResult();

  const validations = [
    { label: "Productos", ok: result.validationSummary.productsValid },
    { label: "Envio", ok: result.validationSummary.shipmentValid },
    { label: "Transportistas", ok: result.validationSummary.carriersValid },
  ];

  return (
    <BackofficeShell
      activeKey="summary"
      title="Vista de entrada del backoffice"
      subtitle="Layout interno separado de la web publica en uis/website."
    >
          <div className="cards">
            <article className="card">
              <h2>Valor inventario</h2>
              <div className="metric">${result.inventoryValueUSD.toLocaleString("es-ES")}</div>
            </article>

            <article className="card">
              <h2>SKUs en low stock</h2>
              <div className="metric">{result.lowStockSkus.length}</div>
            </article>

            <article className="card">
              <h2>Transportista recomendado</h2>
              <div className="metric">
                {result.recommendedCarrier ? result.recommendedCarrier.name : "Sin candidato"}
              </div>
            </article>
          </div>

          <article className="card">
            <h3 className="panel-title">Resultado visible del modulo de logica de negocio (Hito 2)</h3>
            <p>
              Mejor opcion: {result.recommendedCarrier?.name || "N/A"} | Score: {result.recommendedCarrier?.score ?? 0} | Coste estimado: ${result.recommendedCarrier?.costUSD ?? 0}
            </p>
            <ul className="list" style={{ marginTop: "0.8rem" }}>
              {Object.entries(result.categoryCount as Record<string, number>).map(([category, count]) => (
                <li key={category}>
                  {category}: {count.toLocaleString("es-ES")}
                </li>
              ))}
            </ul>
          </article>

          <article className="card">
            <h3 className="panel-title">Validaciones del modulo Hito 2</h3>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
              {validations.map((item) => (
                <span key={item.label} className={item.ok ? "badge-ok" : "badge-warn"}>
                  {item.label}: {item.ok ? "OK" : "Error"}
                </span>
              ))}
            </div>
          </article>
    </BackofficeShell>
  );
}
