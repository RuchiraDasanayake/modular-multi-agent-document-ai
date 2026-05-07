import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui";
import { listLearningSamples, LearningSampleOut } from "@/lib/docaiApi";

interface LearningSummaryTabProps {
  selectedRunId: string | null;
}

export default function LearningSummaryTab({ selectedRunId }: LearningSummaryTabProps) {
  const [samples, setSamples] = useState<LearningSampleOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRunId) {
      setSamples([]);
      setError(null);
      return;
    }
    void loadLearningSamples(selectedRunId);
  }, [selectedRunId]);

  async function loadLearningSamples(runId: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await listLearningSamples(runId);
      setSamples(result.samples);
    } catch (e) {
      setError("Could not load learning samples.");
      setSamples([]);
    } finally {
      setLoading(false);
    }
  }

  if (!selectedRunId) {
    return (
        <Card className="border-amber-500/30 bg-amber-500/10">
        <CardContent className="p-4 text-sm text-amber-300">
          Select a run to view samples.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {loading && (
        <Card className="p-4 text-center text-slate-400">
          Loading samples...
        </Card>
      )}

      {!loading && error && (
        <Card className="p-4 border-red-500/30 bg-red-500/10">
          <p className="text-red-300 text-sm">{error}</p>
        </Card>
      )}

      {!loading && !error && samples.length === 0 && (
        <Card className="p-4 text-sm text-slate-400">
          No learning samples yet.
        </Card>
      )}

      {!loading && !error && samples.length > 0 && (
        <>
          <Card className="overflow-hidden border-white/5">
            <CardContent className="p-0">
              <table className="w-full text-sm text-left border-collapse">
                <thead className="bg-slate-900/80 border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Field</th>
                    <th className="px-4 py-3 font-semibold">Decision</th>
                    <th className="px-4 py-3 font-semibold">Original</th>
                    <th className="px-4 py-3 font-semibold">Corrected</th>
                    <th className="px-4 py-3 font-semibold">Evidence</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Source</th>
                    <th className="px-4 py-3 font-semibold">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-slate-800/30">
                  {samples.map((sample) => (
                    <tr key={sample.sample_id} className="hover:bg-slate-800/50 transition-colors">
                      <td className="px-4 py-3 text-slate-300 font-mono text-xs">{sample.field_name}</td>
                      <td className="px-4 py-3 text-slate-300 text-xs">{sample.decision}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs max-w-xs truncate">{sample.original_value || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs max-w-xs truncate">{sample.corrected_value || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs max-w-xs truncate">{sample.evidence_text || "—"}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{sample.validation_status || "—"}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs font-mono">{sample.source}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{new Date(sample.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
          <p className="text-xs text-slate-400">Samples: {samples.length}</p>
        </>
      )}
    </div>
  );
}
