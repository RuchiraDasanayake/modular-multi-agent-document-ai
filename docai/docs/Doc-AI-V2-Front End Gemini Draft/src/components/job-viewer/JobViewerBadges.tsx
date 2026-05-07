import { FileText } from "lucide-react";
import { Badge, Button } from "@/components/ui";

export function StatusPill({ value }: { value: string }) {
  const isGood = ["Completed", "Profiled", "Strategy Assigned", "Ready"].includes(value);
  const isWarn = ["Needs Review", "Processing"].includes(value);
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${
        isGood ? "text-emerald-400" : isWarn ? "text-amber-400" : "text-slate-400"
      }`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          isGood ? "bg-emerald-400" : isWarn ? "bg-amber-400" : "bg-slate-500"
        }`}
      />
      {value}
    </span>
  );
}

export function ValidationBadge({ status }: { status: string }) {
  const isGood = status === "Valid";
  const isWarn = ["Low Confidence", "Recovered", "Needs Review"].includes(status);
  return (
    <Badge
      variant="outline"
      className={
        isGood
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
          : isWarn
          ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
          : "border-red-500/30 bg-red-500/10 text-red-400"
      }
    >
      {status}
    </Badge>
  );
}

export function ArtifactRow({
  name,
  summary,
  isStub = false,
}: {
  name: string;
  summary: string;
  isStub?: boolean;
}) {
  return (
    <tr className="hover:bg-slate-800/40 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 font-mono text-xs text-cyan-400/80">
          <FileText className="h-3.5 w-3.5 shrink-0 text-slate-500" />
          {name}
          {isStub && (
            <span className="text-[9px] font-bold uppercase text-amber-500/70 bg-amber-500/10 px-1 py-0.5 rounded border border-amber-500/20">
              stub
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-xs text-slate-400">{summary}</td>
      <td className="px-4 py-3 text-right">
        <Button variant="ghost" size="sm" disabled className="text-slate-600 cursor-not-allowed">
          View
        </Button>
      </td>
    </tr>
  );
}
