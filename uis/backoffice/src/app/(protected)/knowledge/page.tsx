import { BackofficeShell } from "@/components/backoffice-shell";
import { KnowledgeQueryPanel } from "@/components/knowledge-query-panel";

export default function KnowledgePage() {
  return (
    <BackofficeShell
      activeKey="knowledge"
      title="Base de conocimiento"
      subtitle="Chatea en tiempo real con el agente de primera linea de TrackFlow — seguimiento, devoluciones y preguntas frecuentes."
    >
      <KnowledgeQueryPanel />
    </BackofficeShell>
  );
}
