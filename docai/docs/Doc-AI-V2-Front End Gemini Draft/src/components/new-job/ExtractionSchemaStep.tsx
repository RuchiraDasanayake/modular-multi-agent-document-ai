import { FileDigit } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { mockSchema } from "@/lib/mockData";

const SCHEMAS = [
  { id: "s1", name: "Invoice Standard v1", version: "1.0" },
  { id: "s2", name: "Invoice Complex v2", version: "2.1" },
];

interface ExtractionSchemaStepProps {
  selectedSchemaId: string;
  onSelect: (id: string) => void;
}

export default function ExtractionSchemaStep({
  selectedSchemaId,
  onSelect,
}: ExtractionSchemaStepProps) {
  const requiredFields = mockSchema.fields.filter((f) => f.required);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <FileDigit className="h-4 w-4 opacity-70" />
          Extraction Schema
        </h2>
        <p className="text-xs text-slate-500">
          Select the schema that controls what fields and tables will be extracted.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {SCHEMAS.map((schema) => {
          const active = selectedSchemaId === schema.id;
          return (
            <button
              key={schema.id}
              type="button"
              onClick={() => onSelect(schema.id)}
              className={`p-4 rounded-lg border text-left transition-all relative ${
                active
                  ? "border-cyan-500 bg-cyan-500/10 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
                  : "border-white/10 bg-slate-900/50 hover:bg-slate-800/80"
              }`}
            >
              {active && (
                <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_5px_rgba(6,182,212,0.8)]" />
              )}
              <p className={`text-sm font-semibold mb-1 ${active ? "text-cyan-400" : "text-slate-200"}`}>
                {schema.name}
              </p>
              <p className="text-[10px] font-mono text-slate-500">Version {schema.version}</p>
            </button>
          );
        })}
      </div>

      {selectedSchemaId === "s1" && (
        <Card className="glass-card border-white/5">
          <CardContent className="p-5 space-y-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Schema Summary — Invoice Standard v1
            </p>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Fields</p>
                <p className="text-lg font-bold text-slate-100">{mockSchema.fields.length}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Tables</p>
                <p className="text-lg font-bold text-slate-100">{mockSchema.tables.length}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Required</p>
                <p className="text-lg font-bold text-slate-100">{requiredFields.length}</p>
              </div>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                Required Fields
              </p>
              <div className="flex flex-wrap gap-2">
                {requiredFields.map((f) => (
                  <span
                    key={f.id}
                    className="text-xs font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20"
                  >
                    {f.name}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Tables</p>
              {mockSchema.tables.map((t) => (
                <div key={t.id} className="text-xs text-slate-400">
                  <span className="font-mono text-slate-300">{t.name}</span>
                  <span className="text-slate-600 ml-2">
                    — {t.columns.length} columns
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
