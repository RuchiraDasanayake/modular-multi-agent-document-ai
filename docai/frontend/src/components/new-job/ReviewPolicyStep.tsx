import { ShieldCheck } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { RunTypeBadge } from "./NewJobBadges";

interface ReviewPolicyStepProps {
  runType: "Training Run" | "Production Run";
  reviewOnLowConfidence: boolean;
  reviewOnValidationFailure: boolean;
  reviewOnRecoveryFailure: boolean;
  onReviewOnLowConfidence: (v: boolean) => void;
  onReviewOnValidationFailure: (v: boolean) => void;
  onReviewOnRecoveryFailure: (v: boolean) => void;
}

function PolicyToggle({
  label,
  description,
  checked,
  onChange,
  locked,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  locked?: boolean;
}) {
  return (
    <label
      className={`flex items-start gap-3 p-3 rounded-lg border transition-all ${
        locked
          ? "border-white/5 bg-slate-900/20 cursor-not-allowed"
          : "border-white/10 bg-slate-900/30 cursor-pointer hover:bg-slate-800/40"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={locked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 rounded border-white/20 bg-slate-900/50 text-cyan-500 focus:ring-cyan-500/50"
      />
      <div>
        <p className={`text-xs font-semibold ${locked ? "text-slate-500" : "text-slate-200"}`}>
          {label}
        </p>
        <p className="text-[10px] text-slate-500 mt-0.5">{description}</p>
      </div>
    </label>
  );
}

export default function ReviewPolicyStep({
  runType,
  reviewOnLowConfidence,
  reviewOnValidationFailure,
  reviewOnRecoveryFailure,
  onReviewOnLowConfidence,
  onReviewOnValidationFailure,
  onReviewOnRecoveryFailure,
}: ReviewPolicyStepProps) {
  const isTraining = runType === "Training Run";

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <ShieldCheck className="h-4 w-4 opacity-70" />
          Review Policy
        </h2>
        <p className="text-xs text-slate-500">Configure when documents enter human review for this job.</p>
      </div>

      <Card className="glass-card border-white/5">
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs text-slate-400">Selected run type:</span>
            <RunTypeBadge runType={runType} />
          </div>

          {isTraining && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded bg-cyan-500/5 border border-cyan-500/20 mb-2">
              <p className="text-[10px] text-cyan-400/80">
                <span className="font-bold">Training Run:</span> Review is required. Reviewer corrections
                become Expected Values and feed future Learning Records.
              </p>
            </div>
          )}

          <PolicyToggle
            label="Review required for all documents"
            description="Every document must pass human review before output is confirmed."
            checked={isTraining ? true : false}
            onChange={() => {}}
            locked={isTraining}
          />
          <PolicyToggle
            label="Review on Low Confidence"
            description="Send to review queue when field confidence falls below threshold."
            checked={reviewOnLowConfidence}
            onChange={onReviewOnLowConfidence}
          />
          <PolicyToggle
            label="Review on Validation Failure"
            description="Send to review queue when validation issues are detected."
            checked={reviewOnValidationFailure}
            onChange={onReviewOnValidationFailure}
          />
          <PolicyToggle
            label="Review on Recovery Failure"
            description="Send to review queue when automatic recovery could not resolve all issues."
            checked={reviewOnRecoveryFailure}
            onChange={onReviewOnRecoveryFailure}
          />

          {isTraining && (
            <p className="text-[10px] text-slate-500 font-mono pt-2 border-t border-white/5">
              Expected Values will be recorded for each reviewed document in this Training Run.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
