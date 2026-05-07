import { Cpu } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { MockBadge } from "./NewJobBadges";
import { mockJobContext } from "@/lib/mockData";

const OCR_OPTIONS = ["PaddleOCR (High Res)", "Tesseract (Fast)", "EasyOCR (Multilingual)"];
const PARSER_OPTIONS = ["Layout-Aware Parser", "Simple Text Parser"];
const MODEL_OPTIONS = ["Qwen 3.5 9B", "Llama 3 8B", "Phi-3 Mini"];
const STRATEGY_MODES = ["Deterministic Strategy Assignment", "Manual Override"];

const CAPABILITIES = [
  { key: "text_output", label: "Text Output", enabled: true },
  { key: "bbox_output", label: "Bounding Box Output", enabled: true },
  { key: "table_detection", label: "Table Detection", enabled: true },
  { key: "json_output", label: "JSON Output", enabled: true },
];

interface RuntimeConfigurationStepProps {
  ocrPreference: string;
  parserPreference: string;
  localModel: string;
  strategyMode: string;
  onOcr: (v: string) => void;
  onParser: (v: string) => void;
  onModel: (v: string) => void;
  onStrategyMode: (v: string) => void;
}

export default function RuntimeConfigurationStep({
  ocrPreference,
  parserPreference,
  localModel,
  strategyMode,
  onOcr,
  onParser,
  onModel,
  onStrategyMode,
}: RuntimeConfigurationStepProps) {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <Cpu className="h-4 w-4 opacity-70" />
          Runtime Configuration
        </h2>
        <p className="text-xs text-slate-500">
          Configure OCR, parser, local model, and strategy mode. Mock only — not wired to execution.
        </p>
      </div>

      <Card className="glass-card border-white/5">
        <CardContent className="p-5 space-y-5">
          <div className="grid grid-cols-2 gap-5">
            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                OCR Preference
              </label>
              <select
                value={ocrPreference}
                onChange={(e) => onOcr(e.target.value)}
                className="w-full text-sm rounded-md border border-white/10 bg-slate-900/50 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors"
              >
                {OCR_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                Parser Preference
              </label>
              <select
                value={parserPreference}
                onChange={(e) => onParser(e.target.value)}
                className="w-full text-sm rounded-md border border-white/10 bg-slate-900/50 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors"
              >
                {PARSER_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  Local Model
                </label>
                <MockBadge />
              </div>
              <select
                value={localModel}
                onChange={(e) => onModel(e.target.value)}
                className="w-full text-sm rounded-md border border-white/10 bg-slate-900/50 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors"
              >
                {MODEL_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
              <p className="text-[10px] text-slate-600 font-mono">
                Default from job context: {mockJobContext.selectedModel}
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                Extraction Strategy Mode
              </label>
              <select
                value={strategyMode}
                onChange={(e) => onStrategyMode(e.target.value)}
                className="w-full text-sm rounded-md border border-white/10 bg-slate-900/50 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-colors"
              >
                {STRATEGY_MODES.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>

          <div className="pt-3 border-t border-white/5">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-3">
              Capabilities
            </p>
            <div className="grid grid-cols-2 gap-2">
              {CAPABILITIES.map((cap) => (
                <div key={cap.key} className="flex items-center gap-2 text-xs">
                  <span className={`w-1.5 h-1.5 rounded-full ${cap.enabled ? "bg-emerald-400" : "bg-slate-600"}`} />
                  <span className="text-slate-400">{cap.label}</span>
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
