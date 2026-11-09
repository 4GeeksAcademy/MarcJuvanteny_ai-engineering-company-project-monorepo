import { stageLabel, statusLabel } from "@/lib/labels";

const STATUS_STYLES: Record<string, string> = {
  received: "bg-sky-50 text-sky-800 ring-sky-200",
  in_progress: "bg-amber-50 text-amber-800 ring-amber-200",
  selected: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  discarded: "bg-slate-100 text-slate-600 ring-slate-200",
};

const base = "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset";

export function StatusBadge({ status }: { status: string }) {
  return <span className={`${base} ${STATUS_STYLES[status] ?? STATUS_STYLES.discarded}`}>{statusLabel(status)}</span>;
}

export function StageBadge({ stage }: { stage: string }) {
  return <span className={`${base} bg-indigo-50 text-indigo-800 ring-indigo-200`}>{stageLabel(stage)}</span>;
}
