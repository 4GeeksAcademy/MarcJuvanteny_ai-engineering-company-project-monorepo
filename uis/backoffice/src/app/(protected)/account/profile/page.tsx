import { AccountProfilePanel } from "@/components/account-profile-panel";
import { BackofficeShell } from "@/components/backoffice-shell";

export default function AccountProfilePage() {
  return (
    <BackofficeShell
      activeKey="account"
      title="Mi cuenta"
      subtitle="Consulta tu email y actualiza tus datos de contacto."
    >
      <AccountProfilePanel />
    </BackofficeShell>
  );
}
