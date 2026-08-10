import { BackofficeShell } from "@/components/backoffice-shell";
import { InventoryOrdersHistoryPanel } from "@/components/inventory-orders-history-panel";

export default function InventoryOrdersPage() {
  return (
    <BackofficeShell
      activeKey="inventory-products"
      title="Inventario · Historial de ordenes"
      subtitle="Consulta todas las entradas y salidas en una vista de solo lectura."
    >
      <InventoryOrdersHistoryPanel />
    </BackofficeShell>
  );
}
