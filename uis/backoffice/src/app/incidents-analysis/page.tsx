import { BackofficeShell } from "@/components/backoffice-shell";
import { IncidentAnalysisPanel } from "@/components/incident-analysis-panel";

export default function IncidentsAnalysisPage() {
  return (
    <BackofficeShell
      activeKey="incidents"
      title="Analisis de incidencias"
      subtitle="Carga un CSV, ejecuta el analisis contra la API y descarga el ultimo resumen en CSV."
    >
      <IncidentAnalysisPanel />
    </BackofficeShell>
  );
}
