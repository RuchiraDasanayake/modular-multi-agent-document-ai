"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui";
import { listRuns, listRunDocuments, listReviewRecords } from "@/lib/docaiApi";

interface StrategyMetrics {
  mode: string | undefined;
  docCount: number;
  reviewedCount: number;
  passRate: number;
}

export function StrategyPerformancePanel() {
  const [strategies, setStrategies] = useState<StrategyMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchStrategies = async () => {
      try {
        const jobId = "job-7089e9094c99";
        const runs = await listRuns(jobId);

        if (!isMounted) return;

        const strategyMap: Record<string | undefined, StrategyMetrics> = {};

        for (const run of runs) {
          if (!isMounted) return;

          try {
            const docs = await listRunDocuments(run.run_id);
            const mode = run.mode || "default";

            if (!strategyMap[mode]) {
              strategyMap[mode] = {
                mode,
                docCount: 0,
                reviewedCount: 0,
                passRate: 0,
              };
            }

            let passCount = 0;

            for (const doc of docs) {
              if (!isMounted) return;

              strategyMap[mode].docCount++;

              try {
                const reviews = await listReviewRecords(run.run_id, doc.document_id);
                if (reviews.length > 0) {
                  strategyMap[mode].reviewedCount++;
                  const latestReview = reviews[reviews.length - 1];
                  if (latestReview.review_status === "approved") {
                    passCount++;
                  }
                }
              } catch {
                // Document may not have reviews
              }
            }

            if (strategyMap[mode].reviewedCount > 0) {
              strategyMap[mode].passRate = Math.round(
                (passCount / strategyMap[mode].reviewedCount) * 100
              );
            }
          } catch (err) {
            console.error(`Failed to fetch docs for run ${run.run_id}:`, err);
          }
        }

        if (isMounted) {
          setStrategies(Object.values(strategyMap).sort((a, b) => b.passRate - a.passRate));
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to fetch strategies:", err);
        if (isMounted) setLoading(false);
      }
    };

    fetchStrategies();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <Card className="border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Strategy Performance
          </h3>
          {loading && <span className="text-[10px] text-slate-500">Loading...</span>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/60 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-3 py-2 font-semibold">Mode</th>
                <th className="px-3 py-2 font-semibold text-right">Documents</th>
                <th className="px-3 py-2 font-semibold text-right">Reviewed</th>
                <th className="px-3 py-2 font-semibold text-right">Validation Pass</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {strategies.map((s) => (
                <tr key={s.mode || "default"} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-3 py-2.5">
                    <p className="text-xs font-mono text-slate-300">{s.mode || "default"}</p>
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono text-slate-400">
                    {s.docCount}
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono text-slate-400">
                    {s.reviewedCount}
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono">
                    <span
                      className={
                        s.passRate >= 80
                          ? "text-emerald-400"
                          : s.passRate >= 60
                            ? "text-amber-400"
                            : "text-red-400"
                      }
                    >
                      {s.passRate}%
                    </span>
                  </td>
                </tr>
              ))}
              {strategies.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-center text-slate-500 text-xs">
                    No strategy data available
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
