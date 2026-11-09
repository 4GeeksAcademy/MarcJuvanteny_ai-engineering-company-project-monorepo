import Link from "next/link";

import { StageBadge, StatusBadge } from "@/components/badges";
import { formatDate } from "@/lib/labels";
import type { Candidate } from "@/types/candidate";

export function CandidateTable({ candidates }: { candidates: Candidate[] }) {
  if (candidates.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
        No hay candidatos que coincidan con los filtros.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-4 py-3">Nombre</th>
            <th scope="col" className="px-4 py-3">Puesto</th>
            <th scope="col" className="px-4 py-3">Estado</th>
            <th scope="col" className="px-4 py-3">Etapa</th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">Postulación</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {candidates.map((candidate) => (
            <tr key={candidate.id} className="hover:bg-slate-50">
              <td className="px-4 py-3">
                <Link href={`/candidates/${candidate.id}`} className="font-medium text-indigo-700 hover:underline">
                  {candidate.full_name}
                </Link>
                <div className="text-xs text-slate-500">{candidate.email}</div>
              </td>
              <td className="px-4 py-3 text-slate-700">{candidate.position}</td>
              <td className="px-4 py-3"><StatusBadge status={candidate.status} /></td>
              <td className="px-4 py-3"><StageBadge stage={candidate.stage} /></td>
              <td className="hidden px-4 py-3 text-slate-600 md:table-cell">{formatDate(candidate.applied_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
