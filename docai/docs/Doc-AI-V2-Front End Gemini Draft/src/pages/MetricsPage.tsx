import { MetricsStubWarning } from "@/components/metrics/MetricsStubWarning";
import { MetricsSummaryCards } from "@/components/metrics/MetricsSummaryCards";
import { RunProgressionTable } from "@/components/metrics/RunProgressionTable";
import { StrategyPerformanceTable } from "@/components/metrics/StrategyPerformanceTable";
import { MetricsEvidencePanel } from "@/components/metrics/MetricsEvidencePanel";

export default function MetricsPage() {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            Metrics
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            Extraction performance evidence for this project. Currently stub data only.
          </p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-7xl mx-auto space-y-5 animate-fade-in" style={{ animationDelay: "0.05s" }}>

          <MetricsStubWarning />

          <MetricsSummaryCards />

          <RunProgressionTable />

          <div className="grid grid-cols-5 gap-5">
            <div className="col-span-3">
              <StrategyPerformanceTable />
            </div>
            <div className="col-span-2">
              <MetricsEvidencePanel />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
