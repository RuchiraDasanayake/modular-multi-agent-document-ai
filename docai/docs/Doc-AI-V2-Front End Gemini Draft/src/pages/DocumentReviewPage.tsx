import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { Button } from "@/components/ui";
import {
  mockDocumentQueue,
  mockSelectedPoliciesByDocumentId,
  mockOcrOutputsByDocumentId,
  mockExtractedOutputsByDocumentId,
  mockValidationReportsByDocumentId,
  mockRecoveryReportsByDocumentId,
  mockDocumentArtifactsByDocumentId,
} from "@/lib/mockData";
import DocumentSourcePanel from "@/components/document-review/DocumentSourcePanel";
import ExtractionStrategyPanel from "@/components/document-review/ExtractionStrategyPanel";
import ExtractedFieldsPanel from "@/components/document-review/ExtractedFieldsPanel";
import ExtractedTablesPanel from "@/components/document-review/ExtractedTablesPanel";
import ValidationIssuesPanel from "@/components/document-review/ValidationIssuesPanel";
import RecoveryAttemptsPanel from "@/components/document-review/RecoveryAttemptsPanel";
import ExpectedValuesPanel from "@/components/document-review/ExpectedValuesPanel";
import ReviewActionsPanel from "@/components/document-review/ReviewActionsPanel";

export default function DocumentReviewPage() {
  const { project_id, job_id, doc_id } = useParams();

  const resolvedDocId = (doc_id && mockDocumentArtifactsByDocumentId[doc_id]) ? doc_id : "doc-2";

  const queuedDocument =
    mockDocumentQueue.find((d) => d.documentId === resolvedDocId) ?? mockDocumentQueue[0];
  const documentProfile = mockDocumentArtifactsByDocumentId[resolvedDocId].documentProfile;
  const ocrOutput = mockOcrOutputsByDocumentId[resolvedDocId];
  const selectedPolicy = mockSelectedPoliciesByDocumentId[resolvedDocId];
  const extractedOutput = mockExtractedOutputsByDocumentId[resolvedDocId];
  const validationReport = mockValidationReportsByDocumentId[resolvedDocId];
  const recoveryReport = mockRecoveryReportsByDocumentId[resolvedDocId];

  const reviewStatusNeedsReview = queuedDocument.reviewStatus === "Needs Review";

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 text-sm">
          <Button variant="ghost" size="sm" className="px-1 hover:text-cyan-400" asChild>
            <Link to={`/projects/${project_id}/jobs/${job_id}`}>
              <ChevronLeft className="h-4 w-4" />
            </Link>
          </Button>
          <span className="text-slate-500 font-mono text-xs">
            Jobs / {job_id} /
          </span>
          <span className="font-semibold text-slate-200">{queuedDocument.filename}</span>
          <span className="text-[9px] font-bold uppercase text-amber-500/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 ml-1">
            Mock Review
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-[10px] font-bold uppercase px-2 py-1 rounded border ${
              reviewStatusNeedsReview
                ? "text-amber-400 bg-amber-500/10 border-amber-500/30"
                : "text-emerald-400 bg-emerald-500/10 border-emerald-500/30"
            }`}
          >
            {queuedDocument.reviewStatus}
          </span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Document Source */}
        <section className="w-2/5 border-r border-white/10 bg-slate-950/50 overflow-hidden flex flex-col">
          <DocumentSourcePanel
            queuedDocument={queuedDocument}
            documentProfile={documentProfile}
            ocrOutput={ocrOutput}
          />
        </section>

        {/* Right: Review panels */}
        <section className="flex-1 overflow-y-auto p-6 space-y-5 bg-slate-900/60 backdrop-blur">
          <ExtractionStrategyPanel selectedPolicy={selectedPolicy} />
          <ExtractedFieldsPanel fields={extractedOutput.fields} />
          <ExtractedTablesPanel tables={extractedOutput.tables} />
          <ValidationIssuesPanel validationReport={validationReport} />
          <RecoveryAttemptsPanel recoveryReport={recoveryReport} />
          <ExpectedValuesPanel
            fields={extractedOutput.fields}
            tables={extractedOutput.tables}
          />
          <ReviewActionsPanel />
        </section>
      </div>
    </div>
  );
}
