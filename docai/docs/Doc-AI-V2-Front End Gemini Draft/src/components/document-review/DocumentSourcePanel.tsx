import { FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { StubBadge, ConfidenceBadge } from "./ReviewBadges";
import type {
  FrontendQueuedDocument,
  FrontendOCROutput,
  FrontendDocumentArtifacts,
} from "@/types/domain";

type DocumentProfile = FrontendDocumentArtifacts["documentProfile"];

interface DocumentSourcePanelProps {
  queuedDocument: FrontendQueuedDocument;
  documentProfile: DocumentProfile;
  ocrOutput: FrontendOCROutput;
}

export default function DocumentSourcePanel({
  queuedDocument,
  documentProfile,
  ocrOutput,
}: DocumentSourcePanelProps) {
  return (
    <div className="h-full flex flex-col p-5 gap-4 overflow-y-auto">
      {/* Metadata */}
      <Card className="glass-card border-white/5 shrink-0">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 opacity-70" />
              Document Source
            </h3>
            {documentProfile.is_stub && <StubBadge />}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Filename
              </p>
              <p className="text-xs font-medium text-slate-200">{queuedDocument.filename}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Document ID
              </p>
              <p className="text-xs font-mono text-slate-400">{queuedDocument.documentId}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Detected Type
              </p>
              <p className="text-xs text-slate-300">{documentProfile.detectedType}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Layout Type
              </p>
              <p className="text-xs text-slate-300">{documentProfile.layoutType}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Quality
              </p>
              <p className={`text-xs font-medium ${documentProfile.qualityBin === "good" ? "text-emerald-400" : "text-amber-400"}`}>
                {documentProfile.qualityBin}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-0.5">
                Queue Status
              </p>
              <p className="text-xs text-slate-300">{queuedDocument.queueStatus}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Document placeholder preview */}
      <div className="shrink-0 bg-slate-900/30 border border-white/5 rounded-lg flex items-center justify-center h-40 text-slate-600 text-xs">
        Document preview not available in mock mode
      </div>

      {/* OCR Output */}
      <Card className="glass-card border-white/5 flex-1 min-h-0">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="flex items-center justify-between mb-3 shrink-0">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              OCR Output
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-slate-500 font-mono">{ocrOutput.engineId}</span>
              <ConfidenceBadge confidence={ocrOutput.confidence} />
              {ocrOutput.is_stub && <StubBadge />}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto bg-slate-900/60 border border-white/5 rounded p-3 text-xs font-mono text-cyan-400/80 whitespace-pre-wrap leading-relaxed">
            {ocrOutput.text}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
