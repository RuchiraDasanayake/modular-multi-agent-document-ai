import { Badge } from "@/components/ui";

export function ValidationStatusBadge({ status }: { status: string }) {
  const isGood = status === "Valid";
  const isWarn = ["Low Confidence", "Recovered", "Needs Review"].includes(status);
  const isDanger = ["Missing", "Failed", "Not Grounded"].includes(status);
  return (
    <Badge
      variant="outline"
      className={
        isGood
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
          : isWarn
          ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
          : isDanger
          ? "border-red-500/30 bg-red-500/10 text-red-400"
          : "border-slate-500/30 bg-slate-500/10 text-slate-400"
      }
    >
      {status}
    </Badge>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = (confidence * 100).toFixed(0);
  const isHigh = confidence >= 0.9;
  const isMed = confidence >= 0.7;
  return (
    <span
      className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${
        isHigh
          ? "bg-emerald-500/10 text-emerald-400"
          : isMed
          ? "bg-amber-500/10 text-amber-400"
          : "bg-red-500/10 text-red-400"
      }`}
    >
      {pct}%
    </span>
  );
}

export function StubBadge() {
  return (
    <span className="text-[9px] font-bold uppercase text-amber-500/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
      stub
    </span>
  );
}
