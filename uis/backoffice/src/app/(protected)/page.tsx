import { BackofficeShell } from "@/components/backoffice-shell";
import { getHito2DashboardResult } from "@/lib/hito2";

const categoryLabels: Record<string, string> = {
  fashion: "Moda",
  electronics: "Electronica",
  cosmetics: "Cosmetica",
  home: "Hogar",
  other: "Otros",
};

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
      title="Resumen"
      subtitle="Estado general de la operacion de un vistazo."
    >
      <div className="cards">
        <article className="card">
          <h2>Valor inventario</h2>
          <div className="metric">${result.inventoryValueUSD.toLocaleString("es-ES")}</div>
        </article>

        <article className="card">
          <h2>SKUs con stock bajo</h2>
          <div className="metric">{result.lowStockSkus.length}</div>
        </article>

        <article className="card">
          <h2>Transportista recomendado</h2>
          <div className="metric">
            {result.recommendedCarrier ? result.recommendedCarrier.name : "Sin candidato"}
          </div>
        </article>
      </div>

      <div className="home-detail-grid">
        <article className="card">
          <h3 className="panel-title">Recomendacion de transporte</h3>
          <p>
            Mejor opcion: <strong>{result.recommendedCarrier?.name || "N/A"}</strong> · Puntuacion{" "}
            {result.recommendedCarrier?.score ?? 0} · Coste estimado ${result.recommendedCarrier?.costUSD ?? 0}
          </p>
          <div className="category-chip-list home-category-chips">
            {Object.entries(result.categoryCount as Record<string, number>).map(([category, count]) => (
              <span key={category} className="category-chip">
                {categoryLabels[category.toLowerCase()] ?? category}: {count.toLocaleString("es-ES")}
              </span>
            ))}
          </div>
        </article>

        <article className="card">
          <h3 className="panel-title">Validacion de datos</h3>
          <div className="category-chip-list">
            {validations.map((item) => (
              <span key={item.label} className={item.ok ? "badge-ok" : "badge-warn"}>
                {item.label}: {item.ok ? "OK" : "Error"}
              </span>
            ))}
          </div>
        </article>
      </div>
    </BackofficeShell>
  );
}
