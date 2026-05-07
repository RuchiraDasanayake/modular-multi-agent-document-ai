"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle } from "lucide-react";
import { listRuns, listRunDocuments, listReviewRecords } from "@/lib/docaiApi";

export function MetricsStubWarning() {
  const [hasRealData, setHasRealData] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const checkForRealData = async () => {
      try {
        const jobId = "job-7089e9094c99";
        const runs = await listRuns(jobId);

        if (!isMounted) return;

        let found = false;
        for (const run of runs) {
          if (!isMounted) return;

          try {
            const docs = await listRunDocuments(run.run_id);
            for (const doc of docs) {
              if (!isMounted) return;

              try {
                const reviews = await listReviewRecords(run.run_id, doc.document_id);
                if (reviews.length > 0) {
                  found = true;
                  break;
                }
              } catch {
                // Skip
              }
            }
            if (found) break;
          } catch (err) {
            console.error(`Error checking run ${run.run_id}:`, err);
          }
        }

        if (isMounted) {
          setHasRealData(found);
          setIsLoading(false);
        }
      } catch (err) {
        console.error("Failed to check for real data:", err);
        if (isMounted) setIsLoading(false);
      }
    };

    checkForRealData();

    return () => {
      isMounted = false;
    };
  }, []);

  if (isLoading) {
    return null;
  }

  if (hasRealData) {
    return (
      <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-emerald-500/8 border border-emerald-500/25 text-emerald-300/90">
        <CheckCircle className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
        <div className="space-y-1">
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-400">
            Real Metrics Active
          </p>
          <p className="text-[11px] text-emerald-300/70 leading-relaxed">
            Metrics are computed from actual review records and run data. Strategy rankings and
            scores reflect real extraction performance.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-500/8 border border-amber-500/25 text-amber-300/90">
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
      <div className="space-y-1">
        <p className="text-xs font-bold uppercase tracking-wider text-amber-400">
          Waiting for Review Data
        </p>
        <p className="text-[11px] text-amber-300/70 leading-relaxed">
          Metrics will activate once documents are processed and reviewed. Real metrics require
          <span className="font-semibold"> review records</span> to exist.
        </p>
      </div>
    </div>
  );
}
