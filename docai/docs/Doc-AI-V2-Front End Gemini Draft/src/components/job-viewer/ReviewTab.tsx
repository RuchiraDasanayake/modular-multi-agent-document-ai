import { Link } from "react-router-dom";
import { CheckSquare, FileText } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";
import { ValidationBadge } from "./JobViewerBadges";
import {
  mockDocumentQueue,
  mockValidationReportsByDocumentId,
  mockRecoveryReportsByDocumentId,
} from "@/lib/mockData";

interface ReviewTabProps {
  projectId?: string;
  jobId?: string;
}

export default function ReviewTab({ projectId, jobId }: ReviewTabProps) {
  const needsReviewDocs = mockDocumentQueue.filter((d) => d.reviewStatus === "Needs Review");

  return (
    <div className="space-y-6 animate-fade-in" style={{ animationDelay: "0.1s" }}>
      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 pt-2 flex items-center">
        <CheckSquare className="mr-2 h-4 w-4 opacity-80" />
        Documents Needing Review
      </h2>
      {needsReviewDocs.length === 0 ? (
        <p className="text-slate-500 text-sm">No documents require review.</p>
      ) : (
        needsReviewDocs.map((doc) => {
          const validation = mockValidationReportsByDocumentId[doc.documentId];
          const recovery = mockRecoveryReportsByDocumentId[doc.documentId];
          return (
            <Card key={doc.documentId} className="overflow-hidden border-white/5">
              <div className="bg-slate-900/60 px-4 py-3 border-b border-white/5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="h-4 w-4 text-amber-400/70" />
                  <span className="text-sm font-medium text-slate-200">{doc.filename}</span>
                  <span className="text-slate-600 font-mono text-xs">{doc.documentId}</span>
                </div>
                <Button variant="ghost" size="sm" asChild className="hover:text-cyan-400">
                  <Link to={`/projects/${projectId}/jobs/${jobId}/document/${doc.documentId}`}>
                    Open Review
                  </Link>
                </Button>
              </div>
              <CardContent className="p-4 space-y-4">
                {validation && validation.issues.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                      Validation Issues
                    </p>
                    <ul className="space-y-1.5">
                      {validation.issues.map((issue, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs">
                          <span className="text-red-400 mt-0.5 shrink-0">•</span>
                          <span className="text-slate-400">
                            <span className="font-mono text-slate-300">{issue.target}</span> —{" "}
                            {issue.message}
                          </span>
                          <ValidationBadge status={issue.status} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {recovery && (
                  <div>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                      Recovery Result
                    </p>
                    <div className="flex flex-wrap gap-4 text-xs text-slate-400">
                      <span>
                        Attempted:{" "}
                        <span className={recovery.attempted ? "text-emerald-400" : "text-slate-500"}>
                          {recovery.attempted ? "Yes" : "No"}
                        </span>
                      </span>
                      <span>
                        Summary: <span className="text-slate-300">{recovery.summary}</span>
                      </span>
                      {recovery.recoveredItems.length > 0 && (
                        <span>
                          Recovered:{" "}
                          <span className="text-emerald-400 font-mono">
                            {recovery.recoveredItems.join(", ")}
                          </span>
                        </span>
                      )}
                      {recovery.failedItems.length > 0 && (
                        <span>
                          Failed:{" "}
                          <span className="text-red-400 font-mono">
                            {recovery.failedItems.join(", ")}
                          </span>
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}
