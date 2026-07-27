import { BackofficeShell } from "@/components/backoffice-shell";
import { ChangePasswordPanel } from "@/components/change-password-panel";

export default function ChangePasswordPage() {
  return (
    <BackofficeShell activeKey="account" title="Cambiar contrasena" subtitle="Actualiza la contrasena de tu cuenta.">
      <ChangePasswordPanel />
    </BackofficeShell>
  );
}
