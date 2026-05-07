"use client";

import { useEffect, useState } from "react";
import { CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { listRuns, listRunDocuments, listReviewRecords } from "@/lib/docaiApi";

interface EvidenceItem {
  name: string;
  description: string;
  currentStatus: "available" | "partial" | "not_available";
}

export function MetricsEvidencePanel() {
  const [evidence, setEvidence] = useState<EvidenceItem[]>([
    {
      name: "Review Records",
      description: "Completed human review for each processed document.",
      currentStatus: "not_available",
    },
    {
      name: "Expected Values",
      description: "Reviewer-confirmed correct output per document field.",
      currentStatus: "not_available",
    },
    {
      name: "Final Outputs",
      description: "Committed extraction result after review and recovery.",
      currentStatus: "not_available",
    },
    {
      name: "Validation Reports",
      description: "Per-document validation pass/fail with issue detail.",
      currentStatus: "not_available",
    },
    {
      name: "Recovery Reports",
      description: "Recovery attempt log and resolved/unresolved items.",
      currentStatus: "not_available",
    },
    {
      name: "Metrics Report",
      description: "Precision, recall, F1, and pass rates computed from final outputs.",
      currentStatus: "not_available",
    },
    {
      name: "Run Log",
      description: "Event-level record of document processing within a job.",
      currentStatus: "not_available",
    },
  ]);

  useEffect(() => {
    let isMounted = true;

    const checkEvidence = async () => {
      try {
        const jobId = "job-7089e9094c99";
        const runs = await listRuns(jobId);

        if (!isMounted) return;

        let hasReviewRecords = false;
        let hasRunDocuments = false;

        for (const run of runs) {
          if (!isMounted) return;

          try {
            const docs = await listRunDocuments(run.run_id);
            if (docs.length > 0) {
              hasRunDocuments = true;
            }

            for (const doc of docs) {
              if (!isMounted) return;

              try {
                const reviews = await listReviewRecords(run.run_id, doc.document_id);
                if (reviews.length > 0) {
                  hasReviewRecords = true;
                  break;
                }
              } catch {
                // Skip
              }
            }

            if (hasReviewRecords && hasRunDocuments) break;
          } catch (err) {
            console.error(`Error checking run ${run.run_id}:`, err);
          }
        }

        if (isMounted) {
          const newEvidence = evidence.map((item) => {
            if (item.name === "Review Records") {
              return { ...item, currentStatus: hasReviewRecords ? "available" : "not_available" };
            }
            if (item.name === "Final Outputs" || item.name === "Validation Reports") {
              return { ...item, currentStatus: hasRunDocuments ? "partial" : "not_available" };
            }
            if (item.name === "Metrics Report" || item.name === "Run Log") {
              return { ...item, currentStatus: hasRunDocuments ? "partial" : "not_available" };
            }
            return item;
          });

          setEvidence(newEvidence);
        }
      } catch (err) {
        console.error("Failed to check evidence:", err);
      }
    };

    checkEvidence();

    return () => {
      isMounted = false;
    };
  }, [evidence]);

  const getStatusIcon = (status: string) => {
    if (status === "available") {
      return <CheckCircle className="h-3.5 w-3.5 text-emerald-400 mt-0.5 shrink-0" />;
    }
    if (status === "partial") {
      return <CheckCircle className="h-3.5 w-3.5 text-amber-400/60 mt-0.5 shrink-0" />;
    }
    return <XCircle className="h-3.5 w-3.5 text-red-400/60 mt-0.5 shrink-0" />;
  };

  const getStatusLabel = (status: string) => {
    if (status === "available") return "available";
    if (status === "partial") return "partial";
    return "not available";
  };

  const getTextClass = (status: string) => {
    if (status === "available") return "text-emerald-300";
    if (status === "partial") return "text-amber-300";
    return "text-slate-300";
  };

  return (
    <Card className="border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">
          Evidence Status
        </h3>
        <p className="text-[10px] text-slate-500 mb-4">
          Real-time availability of required data for metrics computation.
        </p>

        <div className="space-y-2.5">
          {evidence.map((item) => (
            <div key={item.name} className="flex items-start gap-3">
              {getStatusIcon(item.currentStatus)}
              <div>
                <p className={`text-xs font-semibold ${getTextClass(item.currentStatus)}`}>
                  {item.name}
                  <span className="ml-2 text-[9px] font-mono text-slate-600">
                    {getStatusLabel(item.currentStatus)}
                  </span>
                </p>
                <p className="text-[10px] text-slate-600 mt-0.5">{item.description}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-3 border-t border-white/5">
          <p className="text-[10px] font-mono text-slate-600">
            Data from actual runs and reviews. Update as you process documents.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
