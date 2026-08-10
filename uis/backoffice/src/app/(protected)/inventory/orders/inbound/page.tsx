import { BackofficeShell } from "@/components/backoffice-shell";
import { InventoryInboundOrderPanel } from "@/components/inventory-inbound-order-panel";

export default function InventoryInboundOrderPage() {
  return (
    <BackofficeShell
      activeKey="inventory-products"
      title="Inventario · Orden de entrada"
      subtitle="Registra recepciones de stock contra POST /inventory/orders/inbound."
    >
      <InventoryInboundOrderPanel />
    </BackofficeShell>
  );
}
