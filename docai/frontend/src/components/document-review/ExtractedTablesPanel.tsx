import { TableProperties } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { ValidationStatusBadge } from "./ReviewBadges";
import type { FrontendTableOutput } from "@/types/domain";

interface ExtractedTablesPanelProps {
  tables: FrontendTableOutput[];
}

export default function ExtractedTablesPanel({ tables }: ExtractedTablesPanelProps) {
  if (tables.length === 0) {
    return null;
  }

  return (
    <>
      {tables.map((table) => (
        <Card key={table.tableName} className="glass-card border-white/5">
          <CardContent className="p-4">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-4">
              <TableProperties className="h-3.5 w-3.5 opacity-70" />
              Table: {table.tableName}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left border-collapse">
                <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    {Object.keys(table.rows[0]?.columns ?? {}).map((col) => (
                      <th key={col} className="px-3 py-2">
                        {col}
                      </th>
                    ))}
                    <th className="px-3 py-2">Validation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-slate-800/10">
                  {table.rows.map((row) => (
                    <tr key={row.rowIndex} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-3 py-2 text-slate-500 font-mono text-[10px]">
                        {row.rowIndex}
                      </td>
                      {Object.values(row.columns).map((val, ci) => (
                        <td key={ci} className="px-3 py-2 text-slate-200">
                          {val}
                        </td>
                      ))}
                      <td className="px-3 py-2">
                        <ValidationStatusBadge status={row.validationStatus} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ))}
    </>
  );
}
