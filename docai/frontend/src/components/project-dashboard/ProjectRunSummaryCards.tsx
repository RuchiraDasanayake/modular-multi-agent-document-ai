function SummaryCard({
  label,
  value,
  valueClass = "text-slate-200",
}: {
  label: string;
  value: number;
  valueClass?: string;
}) {
  return (
    <div className="glass-card rounded-lg px-4 py-3 border border-white/5">
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</p>
    </div>
  );
}

interface ProjectRunSummaryCardsProps {
  totalJobs: number;
  queuedJobs: number;
  completedRuns: number;
}

export function ProjectRunSummaryCards({
  totalJobs,
  queuedJobs,
  completedRuns,
}: ProjectRunSummaryCardsProps) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <SummaryCard label="Total Jobs" value={totalJobs} />
      <SummaryCard
        label="Queued Jobs (job record status)"
        value={queuedJobs}
        valueClass={queuedJobs > 0 ? "text-amber-400" : "text-slate-500"}
      />
      <SummaryCard label="Completed Runs" value={completedRuns} valueClass="text-emerald-400" />
    </div>
  );
}
