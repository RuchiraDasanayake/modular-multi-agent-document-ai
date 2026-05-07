import { CheckCircle, AlertCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, Button } from "@/components/ui";
import { ExecuteRunResponse } from "@/lib/docaiApi";

interface StartRunStepProps {
  jobName: string;
  stagedFileCount: number;
  isSubmitting: boolean;
  submitStatus: "idle" | "submitting" | "success" | "error";
  submitError?: string;
  createdJobId?: string;
  createdRunId?: string;
  executeResult?: ExecuteRunResponse;
  onSubmit: () => void;
  successJobLink?: string;
}

export default function StartRunStep({
  jobName,
  stagedFileCount,
  isSubmitting,
  submitStatus,
  submitError,
  createdJobId,
  createdRunId,
  executeResult,
  onSubmit,
  successJobLink,
}: StartRunStepProps) {
  const isDisabled =
    isSubmitting ||
    submitStatus === "success" ||
    stagedFileCount === 0 ||
    !jobName.trim();

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <CheckCircle className="h-4 w-4 opacity-70" />
          Start Run
        </h2>
        <p className="text-xs text-slate-500">
          Review your configuration before creating and executing the job.
        </p>
      </div>

      {submitStatus === "error" && submitError && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-medium">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{submitError}</span>
        </div>
      )}

      {submitStatus === "success" ? (
        <Card className="glass-card border-white/5">
          <CardContent className="p-5 space-y-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-3">
              Execution Complete
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                  Job ID
                </p>
                <p className="text-xs font-mono text-slate-200 break-all">
                  {createdJobId || "—"}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                  Run ID
                </p>
                <p className="text-xs font-mono text-slate-200 break-all">
                  {createdRunId || "—"}
                </p>
              </div>
              {executeResult && (
                <>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                      Documents Processed
                    </p>
                    <p className="text-sm font-mono text-slate-200">
                      {executeResult.completed_count}/{executeResult.document_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                      Artifacts Indexed
                    </p>
                    <p className="text-sm font-mono text-slate-200">
                      {executeResult.artifacts_indexed}
                    </p>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="glass-card border-white/5">
          <CardContent className="p-5 space-y-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-3">
              Preflight Summary
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                  Staged Documents
                </p>
                <p className="text-sm font-mono text-slate-200">
                  {stagedFileCount} file{stagedFileCount !== 1 ? "s" : ""}
                </p>
              </div>
              {stagedFileCount === 0 && (
                <div className="col-span-2">
                  <p className="text-[10px] text-amber-400 uppercase tracking-wider font-bold mb-1">
                    ⚠ No files staged
                  </p>
                  <p className="text-xs text-amber-300">
                    Please add documents before submitting.
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-3">
        {submitStatus === "success" ? (
          <>
            {successJobLink ? (
              <Button variant="primary" asChild>
                <Link to={successJobLink}>View Job</Link>
              </Button>
            ) : (
              <Button variant="primary" disabled>
                View Job
              </Button>
            )}
            <span className="text-xs text-emerald-400">
              ✓ Job created and executed successfully
            </span>
          </>
        ) : (
          <Button
            variant="primary"
            disabled={isDisabled}
            onClick={onSubmit}
            className={isSubmitting ? "opacity-75" : ""}
          >
            {isSubmitting
              ? "Creating and Executing..."
              : "Create Job and Execute Run"}
          </Button>
        )}
      </div>
    </div>
  );
}
