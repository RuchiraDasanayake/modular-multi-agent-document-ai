import { UploadCloud, FileText } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";
import { mockDocumentQueue } from "@/lib/mockData";

export default function DocumentQueueStep() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <FileText className="h-4 w-4 opacity-70" />
          Document Queue
        </h2>
        <p className="text-xs text-slate-500">
          Stage documents for this job. Upload is not connected — showing mock queue.
        </p>
      </div>

      {/* Upload placeholder */}
      <div className="border-2 border-dashed border-white/10 rounded-lg p-8 flex flex-col items-center justify-center text-center bg-slate-900/30 hover:bg-slate-800/40 transition-colors group">
        <div className="bg-slate-900 p-3 rounded-full mb-3 group-hover:shadow-[0_0_15px_rgba(6,182,212,0.15)] transition-shadow">
          <UploadCloud className="h-6 w-6 text-cyan-400/60" />
        </div>
        <p className="text-sm font-medium text-slate-400 mb-1">Upload not connected in mock mode</p>
        <p className="text-xs text-slate-600 font-mono mb-3">PDF, PNG, JPG — mock queue shown below</p>
        <Button variant="outline" size="sm" disabled className="border-white/10 text-slate-500 cursor-not-allowed">
          Select Files (Mock)
        </Button>
      </div>

      {/* Mock queue */}
      <Card className="overflow-hidden border-white/5">
        <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400 flex items-center justify-between">
          <span>Queued Documents (Mock)</span>
          <span className="text-slate-500 font-mono font-normal normal-case">
            {mockDocumentQueue.length} documents
          </span>
        </div>
        <CardContent className="p-0">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-2">Filename</th>
                <th className="px-4 py-2">Queue</th>
                <th className="px-4 py-2">Profile</th>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2">Review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {mockDocumentQueue.map((doc) => (
                <tr key={doc.documentId} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
                      <FileText className="h-3.5 w-3.5 text-cyan-400/50 shrink-0" />
                      {doc.filename}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-400">{doc.queueStatus}</td>
                  <td className="px-4 py-2 text-xs text-slate-400">{doc.profileStatus}</td>
                  <td className="px-4 py-2 text-xs text-slate-400">{doc.strategyStatus}</td>
                  <td className="px-4 py-2 text-xs text-slate-400">{doc.reviewStatus}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex gap-6 text-xs text-slate-500">
        <span>
          Total: <span className="text-slate-300 font-mono">{mockDocumentQueue.length}</span>
        </span>
        <span>
          Completed:{" "}
          <span className="text-emerald-400 font-mono">
            {mockDocumentQueue.filter((d) => d.queueStatus === "Completed").length}
          </span>
        </span>
        <span>
          Needs Review:{" "}
          <span className="text-amber-400 font-mono">
            {mockDocumentQueue.filter((d) => d.reviewStatus === "Needs Review").length}
          </span>
        </span>
      </div>
    </div>
  );
}
