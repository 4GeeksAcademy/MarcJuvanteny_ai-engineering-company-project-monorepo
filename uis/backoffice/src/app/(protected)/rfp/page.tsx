import { BackofficeShell } from "@/components/backoffice-shell";
import { RfpIntakePanel } from "@/components/rfp-intake-panel";

export default function RfpIntakePage() {
  return (
    <BackofficeShell
      activeKey="rfp"
      title="Recepcion de RFPs"
      subtitle="Sube una RFP en PDF para crear un ticket y seguir su analisis en tiempo real."
    >
      <RfpIntakePanel />
    </BackofficeShell>
  );
}
