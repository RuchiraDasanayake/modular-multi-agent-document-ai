export function StepStatusBadge({ status }: { status: "active" | "complete" | "pending" }) {
  if (status === "complete") {
    return (
      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-[10px] font-bold">
        ✓
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-500/50 text-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.4)]" />
    );
  }
  return (
    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-800 border border-white/10 text-slate-600" />
  );
}

export function RunTypeBadge({ runType }: { runType: "Training Run" | "Production Run" }) {
  const isTraining = runType === "Training Run";
  return (
    <span
      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${
        isTraining
          ? "text-cyan-400 bg-cyan-500/10 border-cyan-500/30"
          : "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
      }`}
    >
      {runType}
    </span>
  );
}

export function MockBadge() {
  return (
    <span className="text-[9px] font-bold uppercase text-amber-500/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
      mock
    </span>
  );
}
