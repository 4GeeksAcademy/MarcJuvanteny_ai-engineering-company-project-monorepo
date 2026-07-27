import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/components/forgot-password-form";

export const metadata: Metadata = {
  title: "Recuperar contrasena - TrackFlow Backoffice",
};

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
