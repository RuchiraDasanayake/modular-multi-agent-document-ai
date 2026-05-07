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

function reviewBurden(passRate: number): string {
  if (passRate >= 85) return "Low";
  if (passRate >= 65) return "Medium";
  return "High";
}

function reviewBurdenClass(burden: string): string {
  if (burden === "Low") return "text-emerald-400";
  if (burden === "Medium") return "text-amber-400";
  return "text-red-400";
}

export function StrategyPerformanceTable() {
  const [strategies, setStrategies] = useState<StrategyMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const fetchStrategyMetrics = async () => {
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
        console.error("Failed to fetch strategy metrics:", err);
        if (isMounted) setLoading(false);
      }
    };

    fetchStrategyMetrics();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5">
        <span className="text-[10px] uppercase font-bold text-slate-400">
          Strategy Performance
        </span>
      </div>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse whitespace-nowrap">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Mode</th>
                <th className="px-4 py-3 font-semibold text-right">Documents</th>
                <th className="px-4 py-3 font-semibold text-right">Reviewed</th>
                <th className="px-4 py-3 font-semibold text-right">Validation Pass %</th>
                <th className="px-4 py-3 font-semibold">Review Burden</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {strategies.map((s) => {
                const burden = reviewBurden(s.passRate);
                return (
                  <tr key={s.mode || "default"} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <p className="text-xs font-mono text-slate-300">{s.mode || "default"}</p>
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                      {s.docCount}
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                      {s.reviewedCount}
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
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
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold ${reviewBurdenClass(burden)}`}>
                        {burden}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {strategies.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500 text-xs">
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
