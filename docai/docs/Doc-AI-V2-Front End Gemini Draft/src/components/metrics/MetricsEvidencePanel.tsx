import { CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui";

interface EvidenceItem {
  name: string;
  description: string;
  currentStatus: "stub" | "not_available";
}

const REQUIRED_EVIDENCE: EvidenceItem[] = [
  {
    name: "Expected Values",
    description: "Reviewer-confirmed correct output per document field.",
    currentStatus: "not_available",
  },
  {
    name: "Review Records",
    description: "Completed human review for each processed document.",
    currentStatus: "not_available",
  },
  {
    name: "Final Outputs",
    description: "Committed extraction result after review and recovery.",
    currentStatus: "stub",
  },
  {
    name: "Validation Reports",
    description: "Per-document validation pass/fail with issue detail.",
    currentStatus: "stub",
  },
  {
    name: "Recovery Reports",
    description: "Recovery attempt log and resolved/unresolved items.",
    currentStatus: "stub",
  },
  {
    name: "Metrics Report",
    description: "Precision, recall, F1, and pass rates computed from final outputs.",
    currentStatus: "stub",
  },
  {
    name: "Run Log",
    description: "Event-level record of document processing within a job.",
    currentStatus: "stub",
  },
];

export function MetricsEvidencePanel() {
  return (
    <Card className="border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
          Evidence Requirements
        </h3>
        <p className="text-[10px] text-slate-500 mb-4">
          Metrics become real only after this evidence exists in the backend.
        </p>

        <div className="space-y-2.5">
          {REQUIRED_EVIDENCE.map((item) => (
            <div key={item.name} className="flex items-start gap-3">
              {item.currentStatus === "not_available" ? (
                <XCircle className="h-3.5 w-3.5 text-red-400/60 mt-0.5 shrink-0" />
              ) : (
                <CheckCircle className="h-3.5 w-3.5 text-slate-600 mt-0.5 shrink-0" />
              )}
              <div>
                <p
                  className={`text-xs font-semibold ${
                    item.currentStatus === "not_available"
                      ? "text-slate-300"
                      : "text-slate-500"
                  }`}
                >
                  {item.name}
                  <span
                    className={`ml-2 text-[9px] font-mono ${
                      item.currentStatus === "not_available"
                        ? "text-red-400/50"
                        : "text-slate-600"
                    }`}
                  >
                    {item.currentStatus === "not_available" ? "not available" : "stub only"}
                  </span>
                </p>
                <p className="text-[10px] text-slate-600 mt-0.5">{item.description}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-3 border-t border-white/5">
          <p className="text-[10px] font-mono text-slate-600">
            Strategy rankings remain mock-only until Expected Values and review records exist.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
