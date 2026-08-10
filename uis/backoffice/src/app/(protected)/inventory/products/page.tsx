import { BackofficeShell } from "@/components/backoffice-shell";
import { InventoryProductsPanel } from "@/components/inventory-products-panel";

export default function InventoryProductsPage() {
  return (
    <BackofficeShell
      activeKey="inventory-products"
      title="Inventario · Productos"
      subtitle="Consulta el stock actual por producto y crea ordenes de entrada o salida por fila."
    >
      <InventoryProductsPanel />
    </BackofficeShell>
  );
}
