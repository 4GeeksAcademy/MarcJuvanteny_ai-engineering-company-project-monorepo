import { BackofficeShell } from "@/components/backoffice-shell";
import { InventoryOutboundOrderPanel } from "@/components/inventory-outbound-order-panel";

export default function InventoryOutboundOrderPage() {
  return (
    <BackofficeShell
      activeKey="inventory-products"
      title="Inventario · Orden de salida"
      subtitle="Registra despachos o perdidas de stock."
    >
      <InventoryOutboundOrderPanel />
    </BackofficeShell>
  );
}
