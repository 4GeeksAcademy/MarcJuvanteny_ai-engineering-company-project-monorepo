import { Suspense } from "react";

import { CandidateList } from "@/components/candidate-list";
import { LoadingState } from "@/components/feedback";

export default function Home() {
  return (
    <div className="grid grid-cols-1 gap-5">
      <div>
        <h1 className="text-2xl font-semibold">Candidatos</h1>
        <p className="text-sm text-slate-600">Proceso de selección · Asistente de Dirección, sede Zaragoza</p>
      </div>
      {/* useSearchParams solo existe en el cliente: el resto de la página se prerenderiza. */}
      <Suspense fallback={<LoadingState label="Cargando candidatos..." />}>
        <CandidateList />
      </Suspense>
    </div>
  );
}
