import { mockJobsList } from "@/lib/mockData";

function SummaryCard({
  label,
  value,
  valueClass = "text-slate-200",
}: {
  label: string;
  value: number | string;
  valueClass?: string;
}) {
  return (
    <div className="glass-card rounded-lg px-4 py-3 border border-white/5">
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</p>
    </div>
  );
}

export function JobsSummaryCards() {
  const total = mockJobsList.length;
  const trainingRuns = mockJobsList.filter((j) => j.runType === "Training Run").length;
  const productionRuns = mockJobsList.filter((j) => j.runType === "Production Run").length;
  const needsReview = mockJobsList.reduce((sum, j) => sum + j.needsReviewCount, 0);
  const completed = mockJobsList.filter((j) => j.status === "Completed").length;

  return (
    <div className="grid grid-cols-5 gap-3">
      <SummaryCard label="Total Jobs" value={total} />
      <SummaryCard
        label="Training Runs"
        value={trainingRuns}
        valueClass="text-violet-400"
      />
      <SummaryCard
        label="Production Runs"
        value={productionRuns}
        valueClass="text-slate-300"
      />
      <SummaryCard
        label="Needs Review"
        value={needsReview}
        valueClass={needsReview > 0 ? "text-amber-400" : "text-slate-500"}
      />
      <SummaryCard
        label="Completed"
        value={completed}
        valueClass="text-emerald-400"
      />
    </div>
  );
}
