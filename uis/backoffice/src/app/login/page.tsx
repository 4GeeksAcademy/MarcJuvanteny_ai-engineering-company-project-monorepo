import type { Metadata } from "next";

import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = {
  title: "Iniciar sesion - TrackFlow Backoffice",
};

export default function LoginPage() {
  return <LoginForm />;
}
