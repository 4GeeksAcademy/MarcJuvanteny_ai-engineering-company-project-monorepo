import { BackofficeShell } from "@/components/backoffice-shell";
import { KnowledgeQueryPanel } from "@/components/knowledge-query-panel";

export default function KnowledgePage() {
  return (
    <BackofficeShell
      activeKey="knowledge"
      title="Base de conocimiento"
      subtitle="Preguntale al asistente de ventas de TrackFlow — SLA, devoluciones, transportistas y tarifas de almacenamiento."
    >
      <KnowledgeQueryPanel />
    </BackofficeShell>
  );
}
