import { AlertTriangle } from "lucide-react";

export function MetricsStubWarning() {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-500/8 border border-amber-500/25 text-amber-300/90">
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-wider text-amber-400">
          Mock / Stub Metrics Only
        </p>
        <p className="text-[11px] text-amber-300/70 leading-relaxed">
          All values on this page are generated from stub fixtures and do not represent real
          extraction performance. Real metrics require reviewed{" "}
          <span className="font-semibold">Expected Values</span> and backend scoring records to
          exist. Do not treat strategy rankings or scores as production truth.
        </p>
      </div>
    </div>
  );
}
