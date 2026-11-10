import { Suspense } from "react";

import { CandidateDetail } from "@/components/candidate-detail";
import { LoadingState } from "@/components/feedback";

export default function CandidatePage() {
  return (
    <Suspense fallback={<LoadingState label="Cargando candidato..." />}>
      <CandidateDetail />
    </Suspense>
  );
}
