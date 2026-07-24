import { BackofficeShell } from "@/components/backoffice-shell";
import { SuppliersDirectoryPanel } from "@/components/suppliers-directory-panel";

export default function SuppliersPage() {
  return (
    <BackofficeShell
      activeKey="suppliers"
      title="Directorio de proveedores"
      subtitle="Consulta, filtra y actualiza el directorio operativo de USA y Spain sin salir del backoffice."
    >
      <SuppliersDirectoryPanel />
    </BackofficeShell>
  );
}