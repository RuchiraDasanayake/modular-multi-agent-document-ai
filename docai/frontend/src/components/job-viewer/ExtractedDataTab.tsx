import { TableProperties, FileText } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";
import { ValidationBadge } from "./JobViewerBadges";
import { mockExtractedOutputsByDocumentId, mockDocumentQueue } from "@/lib/mockData";

export default function ExtractedDataTab() {
  return (
    <div className="space-y-6 animate-fade-in" style={{ animationDelay: "0.1s" }}>
      <div className="flex justify-between items-center pt-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center">
          <TableProperties className="mr-2 h-4 w-4 opacity-80" />
          Extracted Data
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled title="Mock only — no real export">
            Export JSON
          </Button>
          <Button variant="outline" size="sm" disabled title="Mock only — no real export">
            Export CSV
          </Button>
        </div>
      </div>
      <p className="text-[10px] text-amber-400/70 font-mono">
        Mock only — export buttons are non-functional stubs.
      </p>
      {Object.entries(mockExtractedOutputsByDocumentId).map(([docId, output]) => {
        const filename = mockDocumentQueue.find((d) => d.documentId === docId)?.filename ?? docId;
        return (
          <Card key={docId} className="overflow-hidden border-white/5">
            <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400 flex items-center gap-2">
              <FileText className="h-3 w-3 text-cyan-400/50" />
              {filename}
              <span className="text-slate-600 font-mono font-normal normal-case ml-2">{docId}</span>
            </div>
            <CardContent className="p-0">
              {output.fields.length > 0 && (
                <table className="w-full text-sm text-left border-collapse">
                  <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
                    <tr>
                      <th className="px-4 py-2">Field</th>
                      <th className="px-4 py-2">Value</th>
                      <th className="px-4 py-2">Confidence</th>
                      <th className="px-4 py-2">Validation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 bg-slate-800/10">
                    {output.fields.map((field, i) => (
                      <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-2 text-slate-400 font-mono text-xs">{field.fieldName}</td>
                        <td className="px-4 py-2 text-slate-100 text-xs">{field.value}</td>
                        <td className="px-4 py-2 text-xs font-mono text-slate-400">
                          {(field.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="px-4 py-2">
                          <ValidationBadge status={field.validationStatus} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {output.tables.map((table, ti) => (
                <div key={ti} className="border-t border-white/5">
                  <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400 flex items-center">
                    <TableProperties className="mr-2 h-3 w-3" />
                    Table: {table.tableName}
                  </div>
                  <table className="w-full text-xs text-left border-collapse">
                    <thead className="text-slate-500 uppercase text-[9px] tracking-wider border-b border-white/5 bg-slate-800/20">
                      <tr>
                        <th className="px-4 py-2">Row</th>
                        {Object.keys(table.rows[0]?.columns ?? {}).map((k) => (
                          <th key={k} className="px-4 py-2">
                            {k}
                          </th>
                        ))}
                        <th className="px-4 py-2">Validation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 bg-slate-800/10">
                      {table.rows.map((row) => (
                        <tr key={row.rowIndex} className="hover:bg-slate-800/40 transition-colors">
                          <td className="px-4 py-2 text-slate-500 font-mono text-[10px]">{row.rowIndex}</td>
                          {Object.values(row.columns).map((val, ci) => (
                            <td key={ci} className="px-4 py-2 text-slate-200">
                              {val}
                            </td>
                          ))}
                          <td className="px-4 py-2">
                            <ValidationBadge status={row.validationStatus} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
