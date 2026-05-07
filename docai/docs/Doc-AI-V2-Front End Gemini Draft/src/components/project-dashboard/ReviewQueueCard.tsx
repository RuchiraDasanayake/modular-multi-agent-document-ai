import { Link } from "react-router-dom";
import { AlertTriangle, ChevronRight, FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { mockDocumentQueue, mockValidationReportsByDocumentId } from "@/lib/mockData";

interface ReviewQueueCardProps {
  projectId: string | undefined;
  jobId?: string;
}

export function ReviewQueueCard({ projectId, jobId = "job-1" }: ReviewQueueCardProps) {
  const needsReview = mockDocumentQueue.filter((d) => d.reviewStatus === "Needs Review");
  const validationIssues = needsReview.reduce((sum, doc) => {
    const report = mockValidationReportsByDocumentId[doc.documentId];
    return sum + (report?.issues?.length ?? 0);
  }, 0);

  return (
    <Card className="border-amber-500/10 overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="h-4 w-4 text-amber-400 opacity-80" />
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Review Queue
          </h3>
          {needsReview.length > 0 && (
            <span className="ml-auto text-xs font-bold font-mono text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded">
              {needsReview.length} pending
            </span>
          )}
        </div>

        {needsReview.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">No documents pending review.</p>
        ) : (
          <div className="space-y-2">
            {needsReview.map((doc) => {
              const report = mockValidationReportsByDocumentId[doc.documentId];
              const issueCount = report?.issues?.length ?? 0;
              return (
                <div
                  key={doc.documentId}
                  className="flex items-start gap-3 px-3 py-2.5 rounded-lg bg-slate-900/40 border border-white/5 hover:border-amber-500/20 transition-colors"
                >
                  <FileText className="h-3.5 w-3.5 text-amber-400/50 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-200 truncate">{doc.filename}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[10px] text-amber-400/70">{doc.reviewStatus}</span>
                      {issueCount > 0 && (
                        <span className="text-[10px] font-mono text-slate-500">
                          {issueCount} validation {issueCount === 1 ? "issue" : "issues"}
                        </span>
                      )}
                    </div>
                  </div>
                  <Link
                    to={`/projects/${projectId}/jobs/${jobId}/document/${doc.documentId}`}
                    className="inline-flex items-center gap-1 text-[10px] text-cyan-400/60 hover:text-cyan-400 transition-colors shrink-0"
                  >
                    Open Review
                    <ChevronRight className="h-3 w-3" />
                  </Link>
                </div>
              );
            })}
          </div>
        )}

        {validationIssues > 0 && (
          <p className="text-[10px] text-slate-500 font-mono mt-3 pt-3 border-t border-white/5">
            {validationIssues} validation {validationIssues === 1 ? "issue" : "issues"} across queued documents
          </p>
        )}
      </CardContent>
    </Card>
  );
}
