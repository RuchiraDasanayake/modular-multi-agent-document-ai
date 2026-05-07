const STATUS_STYLES: Record<string, string> = {
  Draft: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  Queued: "bg-slate-500/10 text-slate-300 border-slate-500/30",
  Profiling: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  "Assigning Strategies": "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  Running: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  "Needs Review": "bg-amber-500/10 text-amber-400 border-amber-500/20",
  Completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  Failed: "bg-red-500/10 text-red-400 border-red-500/20",
};

export function RunStatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? "bg-slate-500/10 text-slate-400 border-slate-500/20";
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
