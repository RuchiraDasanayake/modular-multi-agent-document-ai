"use client";

import { useEffect, useState } from "react";
import { listRuns, listReviewRecords, listRunDocuments } from "@/lib/docaiApi";

function SummaryCard({
  label,
  value,
  valueClass = "text-slate-300",
  isLoading = false,
}: {
  label: string;
  value: string | number;
  valueClass?: string;
  isLoading?: boolean;
}) {
  return (
    <div className="glass-card rounded-lg px-4 py-3 border border-white/5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</p>
      </div>
      <p className={`text-2xl font-bold font-mono ${isLoading ? "text-slate-600" : valueClass}`}>
        {isLoading ? "..." : value}
      </p>
    </div>
  );
}

export function MetricsSummaryCards() {
  const [totalRuns, setTotalRuns] = useState(0);
  const [totalDocs, setTotalDocs] = useState(0);
  const [docsReviewed, setDocsReviewed] = useState(0);
  const [validationPassRate, setValidationPassRate] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchMetrics = async () => {
      try {
        const jobId = "job-7089e9094c99";
        const runs = await listRuns(jobId);

        if (!isMounted) return;
        setTotalRuns(runs.length);

        let totalProcessed = 0;
        let totalReviewed = 0;
        let passCount = 0;

        for (const run of runs) {
          if (!isMounted) return;

          try {
            const runDocs = await listRunDocuments(run.run_id);
            totalProcessed += runDocs.length;

            for (const doc of runDocs) {
              if (!isMounted) return;

              try {
                const reviews = await listReviewRecords(run.run_id, doc.document_id);
                if (reviews.length > 0) {
                  totalReviewed++;
                  const latestReview = reviews[reviews.length - 1];
                  if (latestReview.review_status === "approved") {
                    passCount++;
                  }
                }
              } catch {
                // Document may not have reviews
              }
            }
          } catch (err) {
            console.error(`Failed to fetch docs for run ${run.run_id}:`, err);
          }
        }

        if (isMounted) {
          setTotalDocs(totalProcessed);
          setDocsReviewed(totalReviewed);
          setValidationPassRate(totalReviewed > 0 ? Math.round((passCount / totalReviewed) * 100) : 0);
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Failed to fetch metrics:", err);
        if (isMounted) setIsLoading(false);
      }
    };

    fetchMetrics();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="grid grid-cols-5 gap-3">
      <SummaryCard label="Total Runs" value={totalRuns} isLoading={isLoading} />
      <SummaryCard
        label="Docs Processed"
        value={totalDocs.toLocaleString()}
        valueClass="text-slate-300"
        isLoading={isLoading}
      />
      <SummaryCard
        label="Docs Reviewed"
        value={docsReviewed}
        valueClass="text-cyan-400"
        isLoading={isLoading}
      />
      <SummaryCard
        label="Needs Review"
        value={totalDocs - docsReviewed}
        valueClass={totalDocs - docsReviewed > 0 ? "text-amber-400" : "text-slate-500"}
        isLoading={isLoading}
      />
      <SummaryCard
        label="Validation Pass"
        value={validationPassRate > 0 ? `${validationPassRate}%` : "—"}
        valueClass={validationPassRate >= 80 ? "text-emerald-400" : validationPassRate >= 60 ? "text-amber-400" : "text-red-400"}
        isLoading={isLoading}
      />
    </div>
  );
}
