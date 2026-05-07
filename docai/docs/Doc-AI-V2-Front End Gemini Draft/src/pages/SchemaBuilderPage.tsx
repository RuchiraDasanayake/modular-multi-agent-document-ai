import { useState } from "react";
import { Plus, List, Database, Trash2 } from "lucide-react";
import { Button, Card, CardContent, Input } from "@/components/ui";
import { mockSchema } from "@/lib/mockData";

export default function SchemaBuilderPage() {
  const [selectedField, setSelectedField] = useState<string | null>(mockSchema.fields[0].id);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <header className="px-6 py-4 border-b border-border bg-surface flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-text-primary">Extraction Schema Builder</h1>
          <p className="text-xs text-text-secondary mt-1">Define the structure to extract from your documents.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Discard Changes</Button>
          <Button variant="primary">Save Schema</Button>
        </div>
      </header>

      <div className="flex-1 flex flex-col p-6 overflow-hidden">
        <div className="max-w-6xl mx-auto w-full flex-1 flex gap-6 min-h-0">
        {/* Left pane - Structure */}
        <div className="w-80 flex flex-col gap-4 border-r border-border pr-6 shrink-0 overflow-y-auto">
          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-bold text-text-secondary uppercase tracking-wider">Fields</h3>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-text-secondary"><Plus className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-1">
            {mockSchema.fields.map(f => (
              <div 
                key={f.id} 
                onClick={() => { setSelectedField(f.id); setSelectedTable(null); }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm cursor-pointer transition-colors ${selectedField === f.id ? 'bg-primary/20 text-primary font-medium' : 'hover:bg-surface-muted text-text-primary'}`}
              >
                <List className={`h-4 w-4 ${selectedField === f.id ? 'text-primary' : 'text-text-secondary'}`} />
                <span className="flex-1 truncate">{f.name}</span>
                {f.required && <span className="text-[9px] bg-warning/20 text-warning px-1.5 py-0.5 rounded font-bold uppercase tracking-wider">Req</span>}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between mt-4">
            <h3 className="text-[11px] font-bold text-text-secondary uppercase tracking-wider">Tables</h3>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-text-secondary"><Plus className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-1">
            {mockSchema.tables.map(t => (
              <div 
                key={t.id} 
                onClick={() => { setSelectedTable(t.id); setSelectedField(null); }}
                className={`flex flex-col gap-1 px-3 py-1.5 rounded cursor-pointer transition-colors ${selectedTable === t.id ? 'bg-primary/20' : 'hover:bg-surface-muted'}`}
              >
                <div className={`flex items-center gap-2 text-sm ${selectedTable === t.id ? 'text-primary font-medium' : 'text-text-primary'}`}>
                  <Database className={`h-4 w-4 ${selectedTable === t.id ? 'text-primary' : 'text-text-secondary'}`} />
                  <span className="flex-1 truncate">{t.name}</span>
                </div>
                <div className="pl-6 space-y-1 border-l border-primary/30 ml-2 mt-1">
                  {t.columns.map(c => (
                    <div key={c.id} className="text-xs text-text-secondary flex items-center justify-between">
                      <span>{c.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right pane - Editor */}
        <div className="flex-1 overflow-y-auto pb-6">
          {selectedField ? (
            <Card className="max-w-2xl">
              <CardContent className="p-5 space-y-6">
                <div>
                   <h2 className="text-sm font-bold uppercase tracking-wider text-text-secondary">Edit Field</h2>
                </div>
                <div className="space-y-4">
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Display Name</label>
                    <Input defaultValue={mockSchema.fields.find(f => f.id === selectedField)?.name} className="text-[13px]" />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Description</label>
                    <textarea 
                      className="w-full text-[13px] rounded-md border border-border bg-surface px-3 py-2 text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary transition-colors h-20"
                      defaultValue={mockSchema.fields.find(f => f.id === selectedField)?.description}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Data Type</label>
                      <select className="w-full text-[13px] rounded-md border border-border bg-surface px-3 py-2 text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary transition-colors">
                        <option value="string">String</option>
                        <option value="number">Number</option>
                        <option value="currency">Currency</option>
                        <option value="date">Date</option>
                      </select>
                    </div>
                    <div className="space-y-2 flex flex-col justify-end">
                      <label className="flex items-center gap-2 text-sm font-medium text-text-primary h-9 cursor-pointer">
                        <input type="checkbox" className="rounded border-border text-primary focus:ring-primary bg-surface/50" defaultChecked={mockSchema.fields.find(f => f.id === selectedField)?.required} />
                        <span className="text-[13px]">Required Field</span>
                      </label>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : selectedTable ? (
            <Card className="max-w-2xl">
              <CardContent className="p-5 space-y-6">
                <div>
                   <h2 className="text-sm font-bold uppercase tracking-wider text-text-secondary">Edit Table</h2>
                </div>
                <div className="space-y-4">
                  <div className="space-y-1">
                    <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Table Name</label>
                    <Input defaultValue={mockSchema.tables.find(t => t.id === selectedTable)?.name} className="text-[13px]" />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Columns</label>
                    <div className="border border-border rounded divide-y divide-border/50 bg-surface">
                      {mockSchema.tables.find(t => t.id === selectedTable)?.columns.map(c => (
                        <div key={c.id} className="p-2 flex items-center justify-between bg-surface-muted/50 hover:bg-surface-muted transition-colors">
                          <div className="flex gap-2 flex-1">
                            <Input defaultValue={c.name} className="bg-surface h-8 text-[13px]" />
                            <select className="rounded border border-border bg-surface px-2 h-8 text-[13px] focus:outline-none focus:ring-1 focus:ring-primary text-text-primary">
                               <option value="string">String</option>
                               <option value="number">Number</option>
                               <option value="currency">Currency</option>
                            </select>
                          </div>
                          <div className="flex ml-2 gap-1">
                            <Button variant="ghost" size="sm" className="h-8 w-8 text-text-secondary hover:text-danger p-0"><Trash2 className="h-4 w-4" /></Button>
                          </div>
                        </div>
                      ))}
                    </div>
                    <Button variant="outline" size="sm" className="mt-2 w-full border-dashed"><Plus className="mr-1.5 h-4 w-4" /> Add Column</Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-text-secondary">
               <List className="h-10 w-10 mb-4 opacity-20" />
               <p className="text-sm">Select a field or table to edit</p>
            </div>
          )}
        </div>
        </div>
      </div>
    </div>
  );
}
