import { mockRunProgression, mockJobsList } from "@/lib/mockData";
import { MockMetricBadge } from "./MetricsBadges";

function SummaryCard({
  label,
  value,
  valueClass = "text-slate-300",
}: {
  label: string;
  value: string | number;
  valueClass?: string;
}) {
  return (
    <div className="glass-card rounded-lg px-4 py-3 border border-white/5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</p>
        <MockMetricBadge />
      </div>
      <p className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</p>
    </div>
  );
}

export function MetricsSummaryCards() {
  const totalRuns = mockRunProgression.length;
  const docsProcessed = mockRunProgression.reduce((sum, r) => sum + r.docs, 0);
  const docsReviewed = mockRunProgression.reduce((sum, r) => sum + r.reviewed, 0);
  const needsReview = mockJobsList.reduce((sum, j) => sum + j.needsReviewCount, 0);

  return (
    <div className="grid grid-cols-5 gap-3">
      <SummaryCard label="Total Runs" value={totalRuns} />
      <SummaryCard
        label="Docs Processed"
        value={docsProcessed.toLocaleString()}
        valueClass="text-slate-300"
      />
      <SummaryCard
        label="Docs Reviewed"
        value={docsReviewed}
        valueClass="text-cyan-400"
      />
      <SummaryCard
        label="Needs Review"
        value={needsReview}
        valueClass={needsReview > 0 ? "text-amber-400" : "text-slate-500"}
      />
      <SummaryCard label="Validation Pass" value="— (stub)" valueClass="text-slate-500" />
    </div>
  );
}
