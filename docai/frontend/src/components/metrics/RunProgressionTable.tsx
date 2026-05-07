"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui";
import { listRuns, listRunDocuments, listReviewRecords } from "@/lib/docaiApi";
import type { RunOut } from "@/lib/docaiApi";
import { EvidenceStatusBadge } from "./MetricsBadges";
import { RunTypeBadge } from "@/components/jobs/RunTypeBadge";

interface RunMetrics {
  run: RunOut;
  docCount: number;
  reviewedCount: number;
  passRate: number;
}

function deriveEvidenceStatus(reviewed: number, total: number): string {
  if (total === 0) return "No Data";
  if (reviewed === 0) return "Pending Review";
  if (reviewed >= total) return "Fully Reviewed";
  return "Partially Reviewed";
}

export function RunProgressionTable() {
  const [runMetrics, setRunMetrics] = useState<RunMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchRunMetrics = async () => {
      try {
        const jobId = "job-7089e9094c99";
        const runs = await listRuns(jobId);

        if (!isMounted) return;

        const metrics: RunMetrics[] = [];

        for (const run of runs) {
          if (!isMounted) return;

          try {
            const docs = await listRunDocuments(run.run_id);
            let reviewedCount = 0;
            let passCount = 0;

            for (const doc of docs) {
              if (!isMounted) return;

              try {
                const reviews = await listReviewRecords(run.run_id, doc.document_id);
                if (reviews.length > 0) {
                  reviewedCount++;
                  const latestReview = reviews[reviews.length - 1];
                  if (latestReview.review_status === "approved") {
                    passCount++;
                  }
                }
              } catch {
                // Document may not have reviews
              }
            }

            metrics.push({
              run,
              docCount: docs.length,
              reviewedCount,
              passRate: reviewedCount > 0 ? Math.round((passCount / reviewedCount) * 100) : 0,
            });
          } catch (err) {
            console.error(`Failed to fetch metrics for run ${run.run_id}:`, err);
          }
        }

        if (isMounted) {
          setRunMetrics(metrics);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to fetch runs:", err);
        if (isMounted) setLoading(false);
      }
    };

    fetchRunMetrics();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">Run Progression</span>
        {loading && <span className="text-[10px] text-slate-500">Loading...</span>}
      </div>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse whitespace-nowrap">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Run ID</th>
                <th className="px-4 py-3 font-semibold">Run Type</th>
                <th className="px-4 py-3 font-semibold text-right">Documents</th>
                <th className="px-4 py-3 font-semibold text-right">Reviewed</th>
                <th className="px-4 py-3 font-semibold text-right">Validation Pass %</th>
                <th className="px-4 py-3 font-semibold">Evidence Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {runMetrics.map((m) => (
                <tr key={m.run.run_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-200 text-xs font-mono">{m.run.run_id.slice(-8)}</td>
                  <td className="px-4 py-3">
                    <RunTypeBadge runType={m.run.run_type} />
                  </td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-300">{m.docCount}</td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">{m.reviewedCount}</td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                    <span className={m.passRate >= 80 ? "text-emerald-400" : m.passRate >= 60 ? "text-amber-400" : "text-red-400"}>
                      {m.passRate}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <EvidenceStatusBadge
                      status={deriveEvidenceStatus(m.reviewedCount, m.docCount)}
                    />
                  </td>
                </tr>
              ))}
              {runMetrics.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500 text-xs">
                    No runs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
