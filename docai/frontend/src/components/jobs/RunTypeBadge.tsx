export type RunType = "Training Run" | "Production Run";

export function RunTypeBadge({ runType }: { runType: string }) {
  if (runType === "Training Run") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider bg-violet-500/10 text-violet-400 border-violet-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0" />
        Training
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider bg-slate-500/10 text-slate-400 border-slate-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
      Production
    </span>
  );
}
