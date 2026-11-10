import { BackofficeShell } from "@/components/backoffice-shell";
import { IncidentsManagementPanel } from "@/components/incidents-management-panel";

export default function IncidentsManagementPage() {
  return (
    <BackofficeShell
      activeKey="incidents-management"
      title="Gestion de incidencias"
      subtitle="Filtra, actualiza y registra incidencias operativas."
    >
      <IncidentsManagementPanel />
    </BackofficeShell>
  );
}
