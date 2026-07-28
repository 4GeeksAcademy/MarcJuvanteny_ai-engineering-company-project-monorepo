import { BackofficeShell } from "@/components/backoffice-shell";
import { IncidentsManagementPanel } from "@/components/incidents-management-panel";

export default function IncidentsManagementPage() {
  return (
    <BackofficeShell
      activeKey="incidents-management"
      title="Gestion de incidencias"
      subtitle="Registra incidencias, filtra el listado operativo y consulta las metricas agregadas."
    >
      <IncidentsManagementPanel />
    </BackofficeShell>
  );
}
