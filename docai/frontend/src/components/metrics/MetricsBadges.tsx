export type EvidenceStatus = "Stub Only" | "Review Required" | "Ready for Scoring";

const EVIDENCE_STYLES: Record<EvidenceStatus, string> = {
  "Stub Only": "bg-slate-500/10 text-slate-400 border-slate-500/20",
  "Review Required": "bg-amber-500/10 text-amber-400 border-amber-500/20",
  "Ready for Scoring": "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

export function EvidenceStatusBadge({ status }: { status: string }) {
  const cls =
    EVIDENCE_STYLES[status as EvidenceStatus] ??
    "bg-slate-500/10 text-slate-400 border-slate-500/20";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider ${cls}`}
    >
      {status}
    </span>
  );
}

export function MockMetricBadge() {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-amber-500/10 text-amber-400/80 border border-amber-500/20">
      Mock Data
    </span>
  );
}
