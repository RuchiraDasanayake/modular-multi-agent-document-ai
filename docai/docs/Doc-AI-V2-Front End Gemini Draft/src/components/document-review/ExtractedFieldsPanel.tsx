import { useState } from "react";
import { FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { ValidationStatusBadge, ConfidenceBadge } from "./ReviewBadges";
import type { FrontendFieldOutput } from "@/types/domain";

interface ExtractedFieldsPanelProps {
  fields: FrontendFieldOutput[];
}

export default function ExtractedFieldsPanel({ fields }: ExtractedFieldsPanelProps) {
  const [corrections, setCorrections] = useState<Record<string, string>>(
    () => Object.fromEntries(fields.map((f) => [f.fieldName, f.value]))
  );

  const handleChange = (fieldName: string, value: string) => {
    setCorrections((prev) => ({ ...prev, [fieldName]: value }));
  };

  return (
    <Card className="glass-card border-white/5">
      <CardContent className="p-4">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-4">
          <FileText className="h-3.5 w-3.5 opacity-70" />
          Extracted Fields
        </h3>
        <div className="space-y-4">
          {fields.map((field) => {
            const corrected = corrections[field.fieldName] ?? field.value;
            const isDirty = corrected !== field.value;
            return (
              <div key={field.fieldName}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-semibold text-slate-300">
                      {field.fieldName}
                    </label>
                    {isDirty && (
                      <span className="text-[9px] font-bold uppercase text-cyan-400 bg-cyan-500/10 px-1 py-0.5 rounded border border-cyan-500/20">
                        corrected
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ConfidenceBadge confidence={field.confidence} />
                    <ValidationStatusBadge status={field.validationStatus} />
                  </div>
                </div>
                <div className="text-[10px] text-slate-500 font-mono mb-1.5">
                  Extracted: <span className="text-slate-400">{field.value}</span>
                </div>
                {field.evidenceText && (
                  <div className="text-[10px] text-slate-600 font-mono mb-1.5 truncate">
                    Evidence: {field.evidenceText}
                  </div>
                )}
                <input
                  type="text"
                  value={corrected}
                  onChange={(e) => handleChange(field.fieldName, e.target.value)}
                  placeholder="Enter correction..."
                  className={`w-full px-3 py-2 text-xs border bg-slate-900/50 rounded focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 text-slate-100 outline-none font-mono transition-all ${
                    isDirty
                      ? "border-cyan-500/40 bg-cyan-500/5"
                      : "border-white/10"
                  }`}
                />
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-slate-600 font-mono mt-4">
          Corrections are local only — not saved to backend.
        </p>
      </CardContent>
    </Card>
  );
}
