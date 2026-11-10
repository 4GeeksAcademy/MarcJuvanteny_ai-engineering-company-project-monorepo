import type { Metadata } from "next";
import Link from "next/link";
import { Geist } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Talent Pipeline Tracker · TrackFlow",
  description: "Seguimiento de candidatos para Asistente de Dirección, sede Zaragoza.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full bg-slate-100 text-slate-900">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
            <Link href="/" className="font-semibold text-slate-900">
              TrackFlow <span className="font-normal text-slate-500">· Talent Pipeline</span>
            </Link>
            <span className="hidden text-sm text-slate-500 sm:inline">Recursos Humanos · Sede Zaragoza</span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
