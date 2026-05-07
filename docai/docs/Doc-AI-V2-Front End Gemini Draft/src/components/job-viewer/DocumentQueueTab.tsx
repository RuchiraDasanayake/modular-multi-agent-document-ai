import { Link } from "react-router-dom";
import { FileDigit, FileText } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import { StatusPill } from "./JobViewerBadges";
import { mockDocumentQueue } from "@/lib/mockData";

interface DocumentQueueTabProps {
  projectId?: string;
  jobId?: string;
}

export default function DocumentQueueTab({ projectId, jobId }: DocumentQueueTabProps) {
  return (
    <div className="space-y-4 animate-fade-in" style={{ animationDelay: "0.1s" }}>
      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 pt-2 flex items-center">
        <FileDigit className="mr-2 h-4 w-4 opacity-80" />
        Document Queue
      </h2>
      <Card className="overflow-hidden border-white/5">
        <CardContent className="p-0">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 backdrop-blur border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Document ID</th>
                <th className="px-4 py-3 font-semibold">Filename</th>
                <th className="px-4 py-3 font-semibold">Queue</th>
                <th className="px-4 py-3 font-semibold">Profile</th>
                <th className="px-4 py-3 font-semibold">Strategy</th>
                <th className="px-4 py-3 font-semibold">Processing</th>
                <th className="px-4 py-3 font-semibold">Review</th>
                <th className="px-4 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/30">
              {mockDocumentQueue.map((doc) => (
                <tr key={doc.documentId} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{doc.documentId}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 font-medium text-slate-200 text-xs">
                      <FileText className="h-4 w-4 text-cyan-400/50 shrink-0" />
                      {doc.filename}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill value={doc.queueStatus} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill value={doc.profileStatus} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill value={doc.strategyStatus} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill value={doc.processingStatus} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill value={doc.reviewStatus} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" size="sm" asChild className="hover:text-cyan-400">
                      <Link to={`/projects/${projectId}/jobs/${jobId}/document/${doc.documentId}`}>
                        View
                      </Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
