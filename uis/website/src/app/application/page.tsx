import type { Metadata } from "next";
import Link from "next/link";
import dynamic from "next/dynamic";

const QuoteForm = dynamic(
  () => import("@/components/quote-form").then((mod) => mod.QuoteForm),
  {
    loading: () => (
      <p className="rounded-xl border border-sky/30 bg-navy/60 px-4 py-3 text-sm text-sky">
        Cargando formulario...
      </p>
    ),
  }
);

export const metadata: Metadata = {
  title: "TrackFlow - Calcula tu presupuesto",
  description:
    "Formulario de aplicacion para calcular presupuesto de envios TrackFlow.",
};

export default function ApplicationPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "LocalBusiness",
            name: "TrackFlow",
            email: "soporte@trackflow.com",
            telephone: "+34 900 555 123",
            address: {
              "@type": "PostalAddress",
              addressLocality: "Madrid",
              addressCountry: "ES",
            },
          }),
        }}
      />
      <header className="border-b border-sky/20 bg-navy/95 backdrop-blur" role="banner">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="inline-flex items-center gap-3" aria-label="Volver al inicio de TrackFlow">
            <span className="h-9 w-9 overflow-hidden rounded-md border border-white/20 bg-gray-300">
              <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" className="h-full w-full" aria-hidden="true">
                <rect x="0" y="0" width="48" height="48" fill="#d7dbe1" />
                <path d="M6 10H42V22H30V40H18V24L29 16H6Z" fill="#000b2a" />
                <path d="M18 10H30L24 16L18 22Z" fill="#ffffff" />
              </svg>
            </span>
            <span className="font-display text-xl tracking-[-0.03em]">
              Track<span className="text-orange">Flow</span>
            </span>
          </Link>
          <Link href="/" className="text-sm text-sky hover:text-white">
            Volver a la landing
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <section className="mb-10 sm:mb-14" aria-label="Cabecera del formulario">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-orange">
            Formulario de aplicacion
          </p>
          <h1 className="mt-4 font-display text-4xl leading-[1.08] tracking-[-0.03em] sm:text-5xl lg:text-6xl">
            Calcula tu presupuesto ahora
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-sky/90">
            Completa esta encuesta y te enviaremos una propuesta personalizada.
            Campos marcados con * son obligatorios.
          </p>
        </section>

        <section
          className="rounded-2xl border border-sky/20 bg-white/5 p-6 sm:p-9"
          aria-label="Formulario de presupuesto"
        >
          <QuoteForm />
        </section>
      </main>
    </>
  );
}
