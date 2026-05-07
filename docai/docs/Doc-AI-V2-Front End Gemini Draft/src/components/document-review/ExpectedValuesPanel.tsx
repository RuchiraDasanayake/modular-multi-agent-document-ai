import { useState } from "react";
import { AlertTriangle, BookOpen } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import type { FrontendFieldOutput, FrontendTableOutput } from "@/types/domain";

interface ExpectedValuesPanelProps {
  fields: FrontendFieldOutput[];
  tables: FrontendTableOutput[];
}

export default function ExpectedValuesPanel({ fields, tables }: ExpectedValuesPanelProps) {
  const [expectedValues, setExpectedValues] = useState<Record<string, string>>(
    () => Object.fromEntries(fields.map((f) => [f.fieldName, f.value]))
  );

  const handleChange = (fieldName: string, value: string) => {
    setExpectedValues((prev) => ({ ...prev, [fieldName]: value }));
  };

  return (
    <Card className="glass-card border-white/5">
      <CardContent className="p-4">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-3">
          <BookOpen className="h-3.5 w-3.5 opacity-70" />
          Expected Values
        </h3>

        <div className="flex items-start gap-2 px-3 py-2.5 rounded bg-amber-500/5 border border-amber-500/20 mb-4">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[10px] text-amber-400/80">
            Mock only — not saved to backend yet. Expected Values become training targets after human review and approval.
          </p>
        </div>

        <div className="space-y-3">
          {fields.map((field) => (
            <div key={field.fieldName} className="flex items-center gap-3">
              <label className="text-xs font-medium text-slate-400 w-32 shrink-0">
                {field.fieldName}
              </label>
              <input
                type="text"
                value={expectedValues[field.fieldName] ?? field.value}
                onChange={(e) => handleChange(field.fieldName, e.target.value)}
                className="flex-1 px-2.5 py-1.5 text-xs border border-white/10 bg-slate-900/50 rounded focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 text-slate-100 outline-none font-mono transition-all"
              />
            </div>
          ))}
        </div>

        {tables.length > 0 && (
          <div className="mt-4 pt-3 border-t border-white/5">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Table Expected Values
            </p>
            <p className="text-xs text-slate-500 font-mono">
              {tables.map((t) => t.tableName).join(", ")} — row-level expected values not yet supported in mock mode.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
